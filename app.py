from ramp_frontend.wsgi import make_app

app = make_app("/home/rth/projects/ramp/config.yml")

if __name__ == "__main__":
    app.run()
