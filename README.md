# HLS Vegetation Indices (HLS-VI)

Generates suite of Vegetation Indices (VI) for HLS Products.

## Usage

### Generating Vegetation Indices

```plain
vi_generate_indices -i INPUT_DIR -o OUTPUT_DIR -s ID_STRING
```

where:

- `INPUT_DIR` is expected to contain L30 or S30 band geotiffs.
- `OUTPUT_DIR` is the directory to write VI geotiffs, and will be created if it does
  not already exist.
- `ID_STRING` is the HLS granule ID basename with a pattern of
  `HLS.{instrument}.{tile_id}.{acquisition_date}.v{version}`

### Generating CMR Metadata

```plain
vi_generate_metadata -i INPUT_DIR -o OUTPUT_DIR
```

where:

- `INPUT_DIR` is expected to be the same as for the `vi_generate_indices`
  command, and must contain a `.cmr.xml` file containing the granule's CMR
  metadata.
- `OUTPUT_DIR` is expected to be the same as for the `vi_generate_indices`
  command, and this is where the new CMR XML metadata file is written, named the
  same as the input XML file, but with the prefix `HLS` replaced with `HLS-VI`.

## Tests

You can run tests using Docker:

```bash
docker compose run --build tox
```
