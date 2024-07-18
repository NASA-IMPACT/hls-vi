from setuptools import setup

setup(
    name="hls_vi",
    version="0.1",
    packages=["hls_vi"],
    install_requires=[
        "dataclasses",
        "numpy~=1.19.0",
        "rasterio",
        "typing-extensions",
        "geojson",
        "pystac[validation]==1.0.0rc2",
        "untangle",
        "shapely",
    ],
    extras_require={"test": ["black[jupyter]==21.12b0", "flake8", "pytest"]},
    entry_points={
        "console_scripts": [
            "vi_generate_indices=hls_vi.generate_indices:main",
            "vi_generate_metadata=hls_vi.generate_metadata:main",
            "vi_generate_stac_items=hls_vi.generate_stac_items:main",
        ],
    },
)
