import setuptools

install_requires = [
    'numpy',
    'vispy',
    'mercantile',
    'requests',
    'requests_cache',
    'pillow',
]

with open("README.md", "r") as f:
    long_description = f.read()

entry_points={
    'console_scripts': [
        'vismap-example = example:main',
    ]
}

setuptools.setup(
    name="vismap",
    version="0.0.2",
    author="Cody Piersall",
    author_email="cody.piersall@gmail.com",
    description="Tile maps rendered with Vispy",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/codypiersall/vismap",
    packages=['vismap'],
    classifiers=(
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ),
    entry_points=entry_points,
    install_requires=install_requires,
)
