from setuptools import setup

setup(
    name="hls_vi",
    version="1.20",
    packages=["hls_vi"],
    include_package_data=True,
    install_requires=[
        "geojson",
        "importlib_resources",
        "lxml>=3.6.0,<6",
        "numpy",
        # we can't use pystac>=1.12.0 because they did a major/breaking bump to
        # the projection extension (v1.x to v2) that renamed proj:epsg -> proj:code.
        "pystac[validation]>=1.0.0rc2,<1.12.0",
        "rasterio",
        "shapely",
        "untangle",
    ],
    extras_require={
        "test": [
            "black[jupyter]",
            "flake8",
            "mypy",
            "pytest",
            "types-dataclasses",
            "types-untangle",
        ]
    },
    entry_points={
        "console_scripts": [
            "vi_generate_indices=hls_vi.generate_indices:main",
            "vi_generate_metadata=hls_vi.generate_metadata:main",
            "vi_generate_stac_items=hls_vi.generate_stac_items:main",
        ],
    },
)
