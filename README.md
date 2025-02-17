# Sortipy

Sort albums in your spotify library by release date.

No real code so far, only one call to API ("proof of concept").

### Set up a Spotify app project for your API keys

- Follow instructions [here](https://spotipy.readthedocs.io/en/2.25.0/#getting-started).
- Get a spotify client id and client secret.
- In your app's dashboard view, go to settings and add `http://127.0.0.1:9090` to "Redirect URIs"

### Execute sortipy

- Clone this repo and go to the sortipy directory
- Create this `.env` file in the sortipy root directory:
  ```sh
  SPOTIPY_CLIENT_ID=<your-client-id>
  SPOTIPY_CLIENT_SECRET=<your-client-secret>
  SPOTIPY_REDIRECT_URI=http://127.0.0.1:9090
  ```
- (opt.) Create virtual environment and activate it: `python3 -m venv .venv` and `source .venv/bin/activate`
- ~~Install package (`-e` for editable install) `python3 -m pip install [-e] .`~~ (some issues with python3.12 pip dependency management...)
- Install dependencies using `python3 -m pip install spotipy python-dotenv`
- Run `python3 src/sortipy/main.py`