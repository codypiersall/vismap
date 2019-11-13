import setuptools

# have to exec; can't import the package before it's built.
exec(open("vismap/_version.py", encoding="utf-8").read())

install_requires = [
    'numpy',
    'vispy',
    'mercantile',
    'requests',
    'requests_cache',
    'pillow',
]

with open("README.md", "r", encoding='utf-8') as f:
    long_description = f.read()

entry_points = {
    'console_scripts': [
        'vismap-example = vismap.examples.basic:main',
        'vismap-grid = vismap.examples.grid:main',
    ]
}

setuptools.setup(
    name="vismap",
    version=__version__,
    author="Cody Piersall",
    author_email="cody.piersall@gmail.com",
    description="Tile maps rendered with Vispy",
    long_description=long_description,
    license='MIT',
    keywords='vispy plot geography map',
    long_description_content_type="text/markdown",
    url="https://github.com/codypiersall/vismap",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points=entry_points,
    install_requires=install_requires,
    package_data={
        'vismap': ['cat-killer-256x256.png'],
    }
)
