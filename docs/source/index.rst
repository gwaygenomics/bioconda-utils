.. image:: bioconda.png

**Bioconda** is a channel for the conda_ package manager
specializing in bioinformatics software. Bioconda consists of:

- a `repository of recipes`_ hosted on GitHub
- a `build system`_ turning these recipes into conda packages
- a `repository of packages`_ containing over 6000 bioinformatics
  packages ready to use with ``conda install``
- over 600 contributors and 500 members who add, modify, update and
  maintain the recipes

.. _conda: https://conda.io/en/latest/index.html
.. _`repository of recipes`: https://github.com/bioconda/bioconda-recipes
.. _`build system`: https://github.com/bioconda/bioconda-utils
.. _`repository of packages`: https://anaconda.org/bioconda/

The conda package manager makes installing software a vastly more
streamlined process. Conda is a combination of other package managers
you may have encountered, such as pip, CPAN, CRAN, Bioconductor,
apt-get, and homebrew.  Conda is both language- and OS-agnostic, and
can be used to install C/C++, Fortran, Go, R, Python, Java etc
programs on Linux, Mac OSX, and Windows.

Conda allows separation of packages into repositories, or ``channels``.
The main ``defaults`` channel has a large number of common
packages. Users can add additional channels from which to install
software packages not available in the defaults channel. Bioconda is
one such channel specializing in bioinformatics software.

When using Bioconda please **cite our article**:

  Grüning, Björn, Ryan Dale, Andreas Sjödin, Brad A. Chapman, Jillian
  Rowe, Christopher H. Tomkins-Tinch, Renan Valieris, the Bioconda
  Team, and Johannes Köster. 2018. "Bioconda: Sustainable and
  Comprehensive Software Distribution for the Life Sciences". Nature
  Methods, 2018 doi::doi:`10.1038/s41592-018-0046-7`.

Bioconda has been acknowledged by NATURE in their `technology blog`_.

.. _`technology blog`: http://blogs.nature.com/naturejobs/2017/11/03/techblog-bioconda-promises-to-ease-bioinformatics-software-installation-woes

Each package added to Bioconda also has a corresponding Docker
`BioContainer`_ automatically created and uploaded to `Quay.io`_. A
list of these and other containers can be found at the `Biocontainers
Registry`_.

.. _`BioContainer`: https://biocontainers.pro
.. _`Quay.io`: https://quay.io/organization/biocontainers
.. _`BioContainers Registry`: https://biocontainers.pro/#/registry

**Browse packages in the Bioconda channel:** :ref:`recipes`

----

Bioconda is a derivative mark of Anaconda :sup:`®`, a trademark of Anaconda,
Inc registered in the U.S. and other countries.  Anaconda, Inc.
grants permission of the derivative use but is not associated with Bioconda.

The Bioconda channel is sponsored by `Anaconda, Inc <https://www.anaconda.com/>`_
in the form of providing unlimited (in time and space) storage.
Bioconda is supported by `Circle CI <https://circleci.com/>`_ via an open
source plan including free Linux and MacOS builds.


.. _using-bioconda:

Using Bioconda
==============
**Bioconda supports only 64-bit Linux and Mac OSX**.


1. Install conda
----------------
Bioconda requires the conda package manager to be installed. If you have an
Anaconda Python installation, you already have it. Otherwise, the best way to
install it is with the `Miniconda <http://conda.pydata.org/miniconda.html>`_
package. The Python 3 version is recommended.

.. seealso::

    * :ref:`conda-anaconda-minconda`
    * The conda `FAQs <http://conda.pydata.org/docs/faq.html>`_ explain how
      it's easy to use with existing Python installations.


.. _set-up-channels:

2. Set up channels
------------------

After installing conda you will need to add the bioconda channel as well as the
other channels bioconda depends on. **It is important to add them in this
order** so that the priority is set correctly (that is, conda-forge is highest
priority).

The `conda-forge`_ channel contains many general-purpose packages not already
found in the ``defaults`` channel.


::

    conda config --add channels defaults
    conda config --add channels bioconda
    conda config --add channels conda-forge

.. _`conda-forge`: https://conda-forge.org


3. Install packages
-------------------
:ref:`Browse the packages <recipes>` to see what's available.

Bioconda is now enabled, so any packages on the bioconda channel can be installed into the current conda environment::

    conda install bwa

Or a new environment can be created::

    conda create -n aligners bwa bowtie hisat star


4. Join the team
----------------

We invite all parties interested in adding/editing package recipes to join the bioconda team, 
so that their pull requests don't require merging by the core team or other members. To do 
so, please fork our `recipes <https://github.com/bioconda/bioconda-recipes>`_ have a read 
through the `Conda documentation <http://conda.pydata.org/docs/building/recipe.html#conda-recipe-files-overview>`_. 
If you ping `@bioconda/core` in a pull request we will review it and then add you to the team, if you desire.

5. Spread the word
------------------

Consider `adding a badge <_static/badge-generator/>`_ to your posters and presentations to promote
that a tool can be easily installed from Bioconda.


Contributors
============

Core
----

* `Johannes Köster <https://github.com/johanneskoester>`_
* `Ryan Dale <https://github.com/daler>`_
* `Brad Chapman <https://github.com/chapmanb>`_
* `Chris Tomkins-Tinch <https://github.com/tomkinsc>`_
* `Björn Grüning <https://github.com/bgruening>`_
* `Andreas Sjödin <https://github.com/druvus>`_
* `Jillian Rowe <https://github.com/jerowe>`_
* `Renan Valieris <https://github.com/rvalieris>`_
* `Marcel Bargull <https://github.com/mbargull>`_
* `Devon Ryan <https://github.com/dpryan79>`_
* `Elmar Pruesse <https://github.com/epruesse>`_

Team
----

Bioconda has over 600 (as of 2019/1) `contributors
<https://github.com/bioconda/bioconda-recipes/graphs/contributors>`_.


Contributor documentation
-------------------------

The rest of this documentation describes the build system architecture, the
process of creating and testing recipes, and adding recipes to the bioconda
channel.


Contents:

.. toctree::
    :maxdepth: 3

    contributing
    updating
    linting
    faqs
    build-system
    cb3
    developer
