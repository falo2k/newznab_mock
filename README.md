This is a simple mock newznab server for testing clients with specific NZBs.  It only currently implements `get` and `search` endpoints to support [Mylar](https://github.com/mylar3/mylar3).

NZB files should be placed in a folder (default `./nzb_files`), and a json file provided which defines the items to be searched for and what files they correspond to.

Search matching is performed against entry titles by checking that all words in the search (split on string) exist in the title string (case insensitive).

```console
usage: newznab_mock.py [-h] [--host HOST] [--port PORT] [--external-url URL] [--api-key API_KEY] [--nzb-path NZB_PATH] --nzb-config CONFIG

Mock Newznab Server

options:
  -h, --help           show this help message and exit
  --host HOST          Host interface to listen on (default: 0.0.0.0)
  --port PORT          Port to listen on (default: 5000)
  --external-url URL   External address for the server. Ensure this is set if being called from another machine. (default: http://localhost:5000)
  --api-key API_KEY    API key for requests (default: mock_api_key)
  --nzb-path NZB_PATH  Path to directory containing NZB files (default: E:\git\newznab_mock\nzb_files)
  --nzb-config CONFIG  Path to JSON file with NZB metadata (default: None)
```

The configuration JSON file should have the following structure (see [`sample.json`](./sample.json)):
```json
[
  {
    "filename": "example1.nzb",
    "title": "Example NZB 1",
    "size": 12345678,
    "group": "alt.binaries.example",
    "categories": ["5000", "5030"]
  },
  {
    "filename": "example2.nzb",
    "title": "Example NZB 2",
    "size": 87654321,
    "group": "alt.binaries.test",
    "categories": "5040"
  }
]
```

To run the server:
```bash
python newznab_mock.py --api-key your_api_key --nzb-path /path/to/nzbs --json-file metadata.json
```

Example requests:
- Search: `http://localhost:5000/api?t=search&q=example&apikey=your_api_key`
- Get: `http://localhost:5000/api?t=get&id=example1&apikey=your_api_key`


To run the docker container, create a data folder that contains a `nzbs.json` configuration file, and holds any nzbs to be served in a subdirectory called `nzb_files`.

```bash
# Run the container with custom settings
docker run -d \
  -p 5000:5000 \
  -v /path/to/your/data:/data \
  -e EXTERNAL_URL=http://your-server-address:5000 \
  -e API_KEY=your_secret_api_key \
  --name newznab-mock \
  ghcr.io/falo2k/newznab_mock
```
