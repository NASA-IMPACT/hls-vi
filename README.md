# HLS Vegetation Indices (HLS-VI)

Generates suite of Vegetation Indices (VI) for HLS Products.

## Usage

### Generating Vegetation Indices

```plain
vi_generate_indices -i INPUT_DIR -o OUTPUT_DIR
```

where:

- `INPUT_DIR` is expected to be named like
  `HLS.{instrument}.{tile_id}.{acquisition_date}.v{version}` and contain L30 or
  S30 band tifs.
- `OUTPUT_DIR` is the directory to write VI tifs, and will be created if it does
  not already exist.  The name of this directory should be named like
  `INPUT_DIR`, but with the prefix `HLS` replaced with `HLS-VI`.

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
