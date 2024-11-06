from setuptools import setup

setup(
    name="hls_vi",
    version="1.12",
    packages=["hls_vi"],
    include_package_data=True,
    install_requires=[
        "dataclasses",
        "geojson",
        "importlib_resources",
        "lxml==3.6.0",
        "numpy~=1.19.0",
        "pystac[validation]==1.0.0rc2",
        "rasterio",
        "shapely",
        "typing-extensions",
        "untangle",
    ],
    extras_require={
        "test": [
            "black[jupyter]==22.8.0",  # Last version to support Python 3.6 runtime
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
