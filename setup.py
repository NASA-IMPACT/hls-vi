from setuptools import setup

setup(
    name="hls_vi",
    version="0.1",
    packages=["hls_vi"],
    install_requires=[
        "matplotlib",
        "numpy~=1.19.0",
        "rasterio==1.1.3",
        "typing-extensions",
    ],
    extras_require={"test": ["black[jupyter]==21.12b0", "flake8", "pytest"]},
    entry_points={
        "console_scripts": [
            "vi_generate_indexes=hls_vi.generate_indexes:main",
            "vi_generate_cmr_metadata=hls_vi.generate_cmr_metadata:main",
        ],
    },
)
