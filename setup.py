from setuptools import setup

setup(
    name="hls_vi",
    version="0.1",
    packages=["hls_vi"],
    install_requires=[
        "matplotlib",
        "numpy~=1.19.0",
        "rasterio==1.1.3",
    ],
    extras_require={"test": ["black[jupyter]==21.12b0", "flake8", "pytest"]},
    # entry_points={
    #     "console_scripts": ["create_indices=hls_vi.hls_vi:cli"],
    # },
)
