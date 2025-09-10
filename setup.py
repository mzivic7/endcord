import shutil

from Cython.Build import cythonize
from setuptools import Extension, setup

extra_compile_args = [
    "-flto",
    "-O3",
    "-ffast-math",
    "-fomit-frame-pointer",
    "-funroll-loops",
]
extra_link_args = [
    "-flto",
    "-O3",
    "-s",
]

if shutil.which("lld"):
    extra_compile_args.append("-fuse-ld=lld")
    extra_link_args.append("-fuse-ld=lld")

extensions = [
    Extension(
        "endcord_cython.media",
        ["endcord_cython/media.pyx"],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    ),
    Extension(
        "endcord_cython.search",
        ["endcord_cython/search.pyx"],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    ),
    Extension(
        "endcord_cython.tui",
        ["endcord_cython/tui.pyx"],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    ),
    Extension(
        "endcord_cython.pgcurses",
        ["endcord_cython/pgcurses.pyx"],
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    ),
]

setup(
    name="endcord",
    packages=[],
    ext_modules=cythonize(extensions, language_level=3),
)
