from app import app

# This is the file that Oryx looks for by default
application = app

if __name__ == '__main__':
    # When running directly, use development server
    app.run()
else:
    # When running under WSGI (Azure), ensure data is loaded
    from app import update_all, init_scheduler
    init_scheduler() 