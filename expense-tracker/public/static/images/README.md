# Images and custom icons

Put PNG / JPG / SVG / WebP files here, then reference them with `url_for`:

    <img src="{{ url_for('static', filename='images/logo.png') }}"
         alt="BudgetWise logo" width="120" height="40">

Never hard-code `/static/images/logo.png`. `url_for` keeps working if the
static route ever moves, and it is what the rest of the templates use.

## Why not the top-level `static/` folder

`app.py` sets `static_folder='public/static'`, so a file in the repo-root
`static/` directory is never served and every request for it 404s. That
folder is a leftover. This is the one Flask actually serves.

## The other icon folder

`public/icons/` is separate and holds only the PWA install icons named in
`manifest.json` (home-screen icons, apple-touch-icon). Those are served by
the `/icons/<file>` route. App artwork belongs here in `images/`, not there.
