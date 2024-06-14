from pathlib import Path
from xml.etree import ElementTree as ET
import contextlib
import io
import os

import pytest
import rasterio
from hls_vi.generate_metadata import generate_metadata
from hls_vi.generate_indices import read_granule_bands, write_granule_indices


def tifs_equal(tif1: Path, tif2: Path):
    with rasterio.open(tif1) as src1, rasterio.open(tif2) as src2:
        return (
            src1.count == src2.count
            and src1.width == src2.width
            and src1.height == src2.height
            and src1.bounds == src2.bounds
            and src1.crs == src2.crs
            and src1.transform == src2.transform
            # -------------------------------------------------------------------
            # TODO: Uncomment the following line to compare the pixel values
            #       once we have correct test fixture tifs to compare against.
            # -------------------------------------------------------------------
            # and (src1.read() == src2.read()).all()
        )


def remove_element(root: ET.Element, path: str) -> None:
    parent_path = "/".join(path.split("/")[:-1])
    parent = root.find(parent_path)
    child = root.find(path)

    assert parent is not None
    assert child is not None

    parent.remove(child)


def remove_datetime_elements(tree: ET.ElementTree) -> ET.ElementTree:
    root = tree.getroot()

    remove_element(root, "./InsertTime")
    remove_element(root, "./LastUpdate")
    remove_element(root, "./DataGranule/ProductionDateTime")
    remove_element(root, "./Temporal/RangeDateTime/BeginningDateTime")
    remove_element(root, "./Temporal/RangeDateTime/EndingDateTime")

    return tree


def assert_indices_equal(actual_dir: Path, expected_dir: Path):
    actual_tif_paths = sorted(actual_dir.glob("*.tif"))
    actual_tif_names = [path.name for path in actual_tif_paths]
    expected_tif_paths = sorted(expected_dir.glob("*.tif"))
    expected_tif_names = [path.name for path in expected_tif_paths]

    assert actual_tif_names == expected_tif_names

    for actual_tif_path, expected_tif_path in zip(actual_tif_paths, expected_tif_paths):
        assert tifs_equal(actual_tif_path, expected_tif_path)


@pytest.mark.parametrize(
    argnames="input_dir",
    argvalues=[
        "tests/fixtures/HLS.L30.T06WVS.2024120T211159.v2.0",
        "tests/fixtures/HLS.S30.T13RCN.2024128T173909.v2.0",
    ],
)
def test_generate_indices(input_dir, tmp_path: Path):
    write_granule_indices(tmp_path, read_granule_bands(Path(input_dir)))
    assert_indices_equal(tmp_path, Path(input_dir.replace("HLS", "HLS-VI")))


@pytest.mark.parametrize(
    argnames="input_dir,output_dir",
    argvalues=[
        (
            "tests/fixtures/HLS.L30.T06WVS.2024120T211159.v2.0",
            "tests/fixtures/HLS-VI.L30.T06WVS.2024120T211159.v2.0",
        ),
        (
            "tests/fixtures/HLS.S30.T13RCN.2024128T173909.v2.0",
            "tests/fixtures/HLS-VI.S30.T13RCN.2024128T173909.v2.0",
        ),
    ],
)
def test_generate_cmr_metadata(input_dir, output_dir):
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_cmr_xml_basename = f"{os.path.basename(output_dir)}.cmr.xml"
    actual_metadata_path = output_path / output_cmr_xml_basename

    # We keep the expected metadata file outside of the output directory,
    # otherwise it would be overwritten by the actual metadata file.
    expected_metadata_path = Path("tests/fixtures") / output_cmr_xml_basename

    try:
        generate_metadata(input_dir=input_path, output_dir=output_path)

        actual_metadata_tree = remove_datetime_elements(ET.parse(actual_metadata_path))
        expected_metadata_tree = remove_datetime_elements(
            ET.parse(expected_metadata_path)
        )

        actual_metadata = io.BytesIO()
        actual_metadata_tree.write(actual_metadata, encoding="utf-8")

        expected_metadata = io.BytesIO()
        expected_metadata_tree.write(expected_metadata, encoding="utf-8")

        assert (
            actual_metadata.getvalue().decode() == expected_metadata.getvalue().decode()
        )
    finally:
        with contextlib.suppress(FileNotFoundError):
            actual_metadata_path.unlink()
