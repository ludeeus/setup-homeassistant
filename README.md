# setup-homeassistant

_Setup a Home Assistant instance in your GitHub action flow._

This can be usefull for any number of reasons, but espesially for testing where you need to test against a running installation of Home Assistant.

During the run it will validate the configuration, and create a LLAT that can be used for authentication.

## Usage

```yaml
- name: 👷 Setup Home Assistant
  id: homeassistant
  uses: ludeeus/setup-homeassistant@main
```

When this step is complete you will have access to these variables you can use later in your job.

| variable                                           | description                                                                                      |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `${{ steps.homeassistant.outputs.url }}`           | This is the URL to reach the instance.                                                           |
| `${{ steps.homeassistant.outputs.token }}`         | This is a LLAT you can use for autenticated requests.                                            |
| `${{ steps.homeassistant.outputs.containername }}` | This is the name of the container that is running, can be usefull if you need to query the logs. |
| `${{ steps.homeassistant.outputs.username }}`      | The username that can be used to authenticate with the instance.                                 |
| `${{ steps.homeassistant.outputs.password }}`      | The password that can be used to authenticate with the instance.                                 |

## Inputs

Inputs for actions are defined with the `with:` key for the stage configuration, these inputs are valid:

| input         | description                                                                                                     |
| ------------- | --------------------------------------------------------------------------------------------------------------- |
| `tag`         | This can be any valid tag for a `homeassistant/home-assistant` container, the default is `dev`.                 |
| `config-dir`  | Relative path to the configuration directory you want to use, defaults to the root of the repo.                 |
| `retry-limit` | How many times/seconds the action will wait for Home Assistant to start before giving up, `360` is the default. |
| `username`    | Custom username for authentication with the Home Assistant instance. Defaults to a random string.               |
| `password`    | Custom password for authentication with the Home Assistant instance. Defaults to a random string.               |

## Full usage example


```yaml
name: home-assistant-check

on:
  pull_request:
    branches: 
    - main
  push:
    branches: 
    - main

jobs:
  check:
    name: With config-dir
    runs-on: ubuntu-latest
    strategy:
      matrix:
        channel:
          - stable
          - beta
          - dev
    steps:
      - name: 📥 Check out the repository
        uses: actions/checkout@v2

      - name: 👷 Setup Home Assistant
        id: homeassistant
        uses: ludeeus/setup-homeassistant@main
        with:
          tag: ${{ matrix.channel }}
          config-dir: test_configuration

      - name: ✅ Verify API Access
        run: | 
          curl -sSL -f -X GET \
            -H "Authorization: Bearer ${{ steps.homeassistant.outputs.token }}" \
            -H "Content-Type: application/json" \
            ${{ steps.homeassistant.outputs.url }}/api/states

      - name: 📜 Get logs
        run: docker logs ${{ steps.homeassistant.outputs.containername }}
```

## Versions

To use a specific version of this action instead of `main` set the value after `@` in the `uses` definition, like:

```yaml
uses: ludeeus/setup-homeassistant@xx.xx.x
```

If you do this, please enable [dependabot](https://dependabot.com/github-actions/) to help you keep that up to date.
