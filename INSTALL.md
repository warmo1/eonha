# Installation Instructions

## Option 1: HACS (Recommended)

Since this project is set up as a git repository, the easiest way to install it is via HACS (Home Assistant Community Store) if you push this code to GitHub.

1.  **Push the code to GitHub**:
    ```bash
    git add .
    git commit -m "Initial working integration"
    git push origin main
    ```
2.  **Open Home Assistant**.
3.  Go to **HACS** > **Integrations**.
4.  Click the **3 dots** in the top right -> **Custom repositories**.
5.  Add the URL of your repository (e.g., `https://github.com/warmo1/eonha`).
6.  Select **Integration** as the category.
7.  Click **Add**.
8.  The "E.ON Next Home Assistant" integration should appear. Click **Download**.
9.  **Restart Home Assistant**.
10. Go to **Settings** > **Devices & Services** > **Add Integration**.
11. Search for **E.ON Next Home Assistant** and install.

## Option 2: Manual Installation

If you prefer to install manually or are testing locally:

1.  **Locate your Home Assistant configuration directory**.
    *   This is typically `/config` (Home Assistant OS/Supervised).
    *   Or `~/.homeassistant` (Core).
2.  **Copy the `custom_components/eonha` folder**:
    Copy the `eonha` folder from `custom_components` in this project to the `custom_components` folder in your Home Assistant configuration directory.
    
    The final structure should look like this:
    ```
    /config/
      └── custom_components/
          └── eonha/
              ├── manifest.json
              ├── __init__.py
              ├── ...
    ```

3.  **Restart Home Assistant**.
4.  Go to **Settings** > **Devices & Services** > **Add Integration**.
5.  Search for **E.ON Next Home Assistant** and follow the configuration steps.

## Troubleshooting

-   **Dependencies**: Home Assistant *should* automatically install the `eonapi` python library. If logs show errors about missing modules, you may need to check your internet connection or install it manually in the HA container.
-   **Logs**: Check `Settings` > `System` > `Logs` for any errors related to `eonha` or `eonapi`.
