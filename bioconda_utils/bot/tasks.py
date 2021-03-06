"""
Celery Tasks doing the actual work
"""

import logging
import os
import sys
import time
import types
from collections import namedtuple
from enum import Enum
from typing import Tuple, Set
import tempfile
import re
import asyncio

from .worker import celery
from .config import BOT_NAME, BOT_EMAIL, CIRCLE_TOKEN, QUAY_LOGIN, ANACONDA_TOKEN
from .. import utils
from ..recipe import Recipe
from ..githandler import TempBiocondaRepo
from ..githubhandler import CheckRunStatus, CheckRunConclusion
from ..circleci import AsyncCircleAPI
from ..upload import anaconda_upload, skopeo_upload

from celery.exceptions import MaxRetriesExceededError

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


PRInfo = namedtuple('PRInfo', 'installation user repo ref recipes issue_number')

Image = namedtuple('Image', "url name tag")
Package = namedtuple('Package', "arch fname url repodata_md")

Arch = Enum('Arch', 'osx-64 linux-64 noarch')

PACKAGE_RE = re.compile(r"(.*packages)/({})/(.+\.tar\.bz2)$".format('|'.join(a.name for a in Arch)))
IMAGE_RE = re.compile(r".*images/(.+)(?::|%3A)(.+)\.tar\.gz$")

class Checkout:
    # We can't use contextlib.contextmanager because these are async and
    # asyncontextmanager is only available in Python >3.7
    """Async context manager checking out git repo

    Args:
      ref: optional sha checksum to checkout (only if issue_number not given)
      issue_number: optional issue number to checkout (only of ref not given)

    Returns `None` if the checkout failed, otherwise the TempGitHandler object

    >>> with Checkout(ghapi, issue_number) as git:
    >>>   if git is None:
    >>>      print("checkout failed")
    >>>   else:
    >>>      for filename in git.list_changed_files():
    """
    def __init__(self, ghapi, ref=None, issue_number=None):
        self.ghapi = ghapi
        self.orig_cwd = None
        self.git = None
        self.ref = ref
        self.issue_number = issue_number

    async def __aenter__(self):
        try:
            if self.issue_number:
                prs = await self.ghapi.get_prs(number=self.issue_number)
                fork_user = prs['head']['user']['login']
                fork_repo = prs['head']['repo']['name']
                branch_name = prs['head']['ref']
                ref = None
            else:
                fork_user = None
                fork_repo = None
                branch_name = "unknown"
                ref = self.ref

            self.git = TempBiocondaRepo(
                password=self.ghapi.token,
                home_user=self.ghapi.user,
                home_repo=self.ghapi.repo,
                fork_user=fork_user,
                fork_repo=fork_repo
            )

            self.git.set_user(BOT_NAME, BOT_EMAIL)

            self.orig_cwd = os.getcwd()
            os.chdir(self.git.tempdir.name)

            branch = self.git.create_local_branch(branch_name, ref)
            if not branch:
                raise RuntimeError(f"Failed to find {branch_name}:{ref} in {self.git}")
            branch.checkout()

            return self.git
        except Exception:
            logger.exception(f"Error while checking out with {self.ghapi}")
            return None

    async def __aexit__(self, _exc_type, _exc, _tb):
        if self.orig_cwd:
            os.chdir(self.orig_cwd)
        if self.git:
            self.git.close()


@celery.task(acks_late=True, ignore_result=False)
async def get_latest_pr_commit(issue_number: int, ghapi):
    """Returns last commit"""
    commit = {'sha': None}
    async for commit in ghapi.iter_pr_commits(issue_number):
        pass
    logger.info("Latest SHA on #%s is %s", issue_number, commit['sha'])
    return commit['sha']


@celery.task(acks_late=True)
async def create_check_run(head_sha: str, ghapi, recreate=True):
    if head_sha is None:
        logger.info("Not creating check_run, SHA is None")
        return
    LINT_CHECK_NAME = "Linting Recipe(s)"
    if not recreate:
        for check_run in await ghapi.get_check_runs(head_sha):
            if check_run.get('name') == LINT_CHECK_NAME:
                logger.warning("Check run for %s exists - not recreating",
                               head_sha)
                return
    check_run_number = await ghapi.create_check_run(LINT_CHECK_NAME, head_sha)
    logger.warning("Created check run %s for %s", check_run_number, head_sha)


@celery.task(acks_late=True)
async def bump(issue_number: int, ghapi):
    """Bump the build number in each recipe"""
    logger.info("Processing bump command: %s", issue_number)
    async with Checkout(ghapi, issue_number=issue_number) as git:
        if not git:
            logger.error("Failed to checkout")
            return
        recipes = git.get_changed_recipes()
        for meta_fn in recipes:
            recipe = Recipe.from_file('recipes', meta_fn)
            recipe.reset_buildnumber(recipe.build_number + 1)
            recipe.save()
        msg = f"Bump {recipe} buildno to {buildno}"
        if not git.commit_and_push_changes(recipes, None, msg, sign=True):
            logger.error("Failed to push?!")


@celery.task(acks_late=True)
async def lint_check(check_run_number: int, ref: str, ghapi):
    """Execute linter
    """
    ref_label = ref[:8] if len(ref) >= 40 else ref
    logger.info("Starting lint check for %s", ref_label)
    await ghapi.modify_check_run(check_run_number, status=CheckRunStatus.in_progress)

    async with Checkout(ghapi, ref=ref) as git:
        if not git:
            await ghapi.modify_check_run(
                check_run_number,
                status=CheckRunStatus.completed,
                conclusion=CheckRunConclusion.cancelled,
                output_title=
                f"Failed to check out "
                f"{ghapi.user}/{ghapi.repo}:{ref_label}"
            )
            return

        recipes = git.get_recipes_to_build()
        if not recipes:
            await ghapi.modify_check_run(
                check_run_number,
                status=CheckRunStatus.completed,
                conclusion=CheckRunConclusion.neutral,
                output_title="No recipes modified",
                output_summary=
                "This branch does not modify any recipes! "
                "Please make sure this is what you intend. Upon merge, "
                "no packages would be built."
            )
            return

        # Here we call the actual linter code
        utils.load_config('config.yml')
        from bioconda_utils.linting import lint as _lint, LintArgs, markdown_report

        # Workaround celery/billiard messing with sys.exit
        if isinstance(sys.exit, types.FunctionType):
            def new_exit(args=None):
                raise SystemExit(args)
            (sys.exit, old_exit) = (new_exit, sys.exit)

            try:
                df = _lint(recipes, LintArgs())
            except SystemExit as exc:
                old_exit(exc.args)
            finally:
                sys.exit = old_exit

        else:
            df = _lint(recipes, LintArgs())

    summary = "Linted recipes:\n"
    for recipe in recipes:
        summary += " - `{}`\n".format(recipe)
    summary += "\n"
    annotations = []
    if df is None:
        conclusion = CheckRunConclusion.success
        title = "All recipes in good condition"
        summary += "No problems found."
    else:
        conclusion = CheckRunConclusion.failure
        title = "Some recipes had problems"
        summary += "Please fix the issues listed below."

        for _, row in df.iterrows():
            check = row['check']
            info = row['info']
            recipe = row['recipe']
            annotations.append({
                'path': recipe + '/meta.yaml',
                'start_line': info.get('start_line', 1),
                'end_line': info.get('end_line', 1),
                'annotation_level': 'failure',
                'title': check,
                'message': info.get('fix') or str(info)
            })

    await ghapi.modify_check_run(
        check_run_number,
        status=CheckRunStatus.completed,
        conclusion=conclusion,
        output_title=title,
        output_summary=summary,
        output_text=markdown_report(df),
        output_annotations=annotations)


@celery.task(acks_late=True)
async def check_circle_artifacts(pr_number: int, ghapi):
    logger.info("Starting check for artifacts on #%s as of %s", pr_number, ghapi)
    pr = await ghapi.get_prs(number=pr_number)
    head_ref = pr['head']['ref']
    head_sha = pr['head']['sha']
    head_user = pr['head']['repo']['owner']['login']
    # get path for Circle
    if head_user == ghapi.user:
        branch = head_ref
    else:
        branch = "pull/{}".format(pr_number)

    capi = AsyncCircleAPI(ghapi.session)
    artifacts = await capi.get_artifacts(branch, head_sha)
    artifact_urls = set(a[1] for a in artifacts)

    packages = []
    images = []
    repos = {}

    for path, url, buildno in artifacts:
        match = PACKAGE_RE.match(url)
        if match:
            # base     /fname
            # repo/arch/fname
            repo_url, arch, fname = match.groups()
            repodata_url = '/'.join((repo_url, arch, 'repodata.json'))
            repodata_md = ""
            if repodata_url in artifact_urls:
                repos.setdefault(repo_url, set()).add(arch)
                repodata_md = "[repodata.json]({})".format(repodata_url)
            packages.append(Package(arch, fname, url, repodata_md))
            continue
        match = IMAGE_RE.match(url)
        if match:
            name, tag = match.groups()
            images.append(Image(url, name, tag))

    tpl = utils.jinja.get_template("artifacts.md")
    msg = tpl.render(packages=packages, repos=repos, images=images)

    msg_head, _, _ = msg.partition("\n")
    async for comment in await ghapi.iter_comments(pr_number):
        if comment['body'].startswith(msg_head):
            await ghapi.update_comment(comment["id"], msg)
            break
    else:
        await ghapi.create_comment(pr_number, msg)


@celery.task(acks_late=True)
async def trigger_circle_rebuild(pr_number: int, ghapi):
    logger.info("Triggering rebuild of #%s", pr_number)
    pr = await ghapi.get_prs(number=pr_number)
    head_ref = pr['head']['ref']
    head_sha = pr['head']['sha']
    head_user = pr['head']['repo']['owner']['login']

    capi = AsyncCircleAPI(ghapi.session, token=CIRCLE_TOKEN)
    if head_user == ghapi.user:
        path = head_ref
    else:
        path = "pull/{}".format(pr_number)

    res = await capi.trigger_rebuild(path, head_sha)
    logger.warning("Trigger_rebuild call returned with %s", res)


@celery.task(bind=True, acks_late=True, ignore_result=False)
async def merge_pr(self, pr_number: int, comment_id: int, ghapi) -> Tuple[bool, str]:
    pr = await ghapi.get_prs(number=pr_number)
    state, message = await ghapi.check_protections(pr_number, pr['head']['sha'])
    if state is None:
        try:
            raise self.retry(countdown=20, max_retries=15)
        except MaxRetriesExceededError:
            return False, "PR cannot be merged at this time. Please try again later"
    if not state:
        return state, message
    comment = ("Upload & Merge started. Reload page to view progress.\n"
               "- [x] Checks OK\n")
    await ghapi.update_comment(comment_id, comment)

    head_ref = pr['head']['ref']
    head_sha = pr['head']['sha']
    head_user = pr['head']['repo']['owner']['login']
    # get path for Circle
    if head_user == ghapi.user:
        branch = head_ref
    else:
        branch = "pull/{}".format(pr_number)

    lines = []

    capi = AsyncCircleAPI(ghapi.session, token=CIRCLE_TOKEN)
    artifacts = await capi.get_artifacts(branch, head_sha)
    files = []
    images = []
    packages = []
    for path, url, buildno in artifacts:
        match = PACKAGE_RE.match(url)
        if match:
            repo_url, arch, fname = match.groups()
            fpath = os.path.join(arch, fname)
            files.append((url, fpath))
            packages.append(fpath)
            continue
        match = IMAGE_RE.match(url)
        if match:
            name, tag = match.groups()
            fname = f"{name}__{tag}.tar.gz"
            files.append((url, fname))
            images.append((fname, f"{name}:{tag}"))

    if not files:
        return False, "PR did not build any packages."

    comment += "- [x] Fetching {} packages and {} images\n".format(len(packages), len(images))
    await ghapi.update_comment(comment_id, comment)

    logger.info("Downloading %s", ', '.join(f for _, f in files))
    done = False
    with tempfile.TemporaryDirectory() as tmpdir:
        ### Download files
        try:
            fds = []
            urls = []
            for url,path in files:
                fpath = os.path.join(tmpdir, path)
                fdir = os.path.dirname(fpath)
                if not os.path.exists(fdir):
                    os.makedirs(fdir)
                urls.append(url)
                fds.append(open(fpath, "wb"))
            await utils.AsyncRequests.async_fetch(urls, fds=fds)
            done = True
            logger.error("Done downloading")
        finally:
            for fd in fds:
                fd.close()
        if not done:
            return False, "Failed to download archives. Please try again later"

        ### Upload Images
        uploaded = []
        for fname, dref in images:
            fpath = os.path.join(tmpdir, fname)
            ndref = "biocontainers/"+dref
            for _ in range(5):
                logger.info("Uploading: %s", ndref)
                if skopeo_upload(fpath, ndref, creds=QUAY_LOGIN):
                    break
                logger.warning("Skopeo upload failed, retrying in 5s...")
                await asyncio.sleep(5)
            else:
                logger.warning("Skopeo upload failed, giving up")
                return False, "Failed to upload image to Quay.io"
            uploaded.append(ndref)
            comment += "- [x] Uploaded image {}\n".format(ndref)
            await ghapi.update_comment(comment_id, comment)

        ### Upload Packages
        for fname in packages:
            fpath = os.path.join(tmpdir, fname)
            for _ in range(5):
                logger.info("Uploading: %s", fname)
                if anaconda_upload(fpath, token=ANACONDA_TOKEN):
                    break
                logger.warning("Anaconda upload failed, retrying in 5s...")
                await asyncio.sleep(5)
            else:
                logger.error("Anaconda upload failed, giving up.")
                return False, "Failed to upload package to Anaconda"
            uploaded.append(fname)
            comment += "- [x] Uploaded package {}\n".format(fname)
            await ghapi.update_comment(comment_id, comment)

        lines.append("")
        lines.append("Package uploads complete: [ci skip]")
        for pkg in uploaded:
            lines.append(" - " + pkg)
        lines.append("")

    # collect authors
    pr_author = pr['user']['login']
    coauthors: Set[str] = set()
    coauthor_logins: Set[str] = set()
    last_sha: str = None
    async for commit in ghapi.iter_pr_commits(pr_number):
        last_sha = commit['sha']
        author_login = (commit['author'] or {}).get('login')
        if author_login != pr_author:
            name = commit['commit']['author']['name']
            email = commit['commit']['author']['email']
            coauthors.add(f"Co-authored-by: {name} <{email}>")
            if author_login:
                coauthor_logins.add("@"+author_login)
            else:
                coauthor_logins.add(name)
    lines.extend(list(coauthors))

    message = "\n".join(lines)
    comment += "- Creating squash merge"
    if coauthors:
        comment += " (with co-authors {})".format(", ".join(coauthor_logins))
    comment += "\n"
    await ghapi.update_comment(comment_id, comment)

    return  await ghapi.merge_pr(pr_number, sha=last_sha,
                                 message="\n".join(lines) if lines else None)

@celery.task(acks_late=True, ignore_result=True)
async def post_result(result: Tuple[bool, str], pr_number: int, comment_id: int, prefix: str, user: str, ghapi) -> None:
    logger.error("post result: result=%s, issue=%s", result, pr_number)
    status = "succeeded" if result[0] else "failed"
    message = f"@{user}, your request to {prefix} {status}: {result[1]}"
    await ghapi.create_comment(pr_number, message)
    logger.warning("message %s", message)
