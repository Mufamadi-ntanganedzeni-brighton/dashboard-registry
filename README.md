# Dashboard Registry

This is a web app I built as part of my Mindworx learnership project. The idea is simple - companies have too many dashboards spread across different tools and nobody knows which one shows what. This app gives everyone one place to go to find the right dashboard quickly.

Think of it like a library catalogue but for dashboards. The app does not show the actual dashboards, it just stores information about them so people can find them easily.

## What you can do in the app

There are two screens.

On the Dashboards screen you can see all dashboards in a table, search by name, filter by category or status, add a new dashboard, edit or delete one, and open the real dashboard link in a new tab. When you add or edit a dashboard you can also choose which data sources it uses.

On the Data Sources screen you can see all the databases, files, and APIs that dashboards depend on. You can add, edit, or delete them. If you try to delete one that is still linked to a dashboard, the app will stop you and show an error.

## How to run it

Install the requirements first:

```
pip install flask flask-cors
```

Then run the backend:

```
python app.py
```

Then open index.html in your browser. The app comes with some sample data already loaded so you can see it working straight away.

## Tech stack

Frontend is HTML, CSS and JavaScript. Backend is Python with Flask. Database is SQLite.

## Design decisions

I chose to block the delete on data sources if they are still linked to dashboards instead of automatically removing the links. That way nothing breaks without the user knowing about it.

Status on a new dashboard defaults to Unknown until someone sets it properly.

## GitHub

https://github.com/Mufamadi-ntanganedzeni-brighton/dashboard-registry
