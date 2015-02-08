#!/usr/bin/env python2

import pandas as pd
import os.path
from git import Repo, Submodule
from flask import Flask, request, redirect, url_for, render_template
from Submission.generic import leaderboard_classical, leaderboard_to_html

app = Flask(__name__)
repo = Repo('TeamsRepos')

@app.route("/register/")
@app.route("/list/")
def list_submodules():
    if len(repo.submodules) == 0:
        return render_template('list.html', submodules=repo.submodules)
        # return "No submodule found"
    else:
        html_list = "<ul>"
        return render_template('list.html', submodules=repo.submodules)

@app.route("/leaderboad/")
def show_leaderboard():
    trained_models = pd.read_csv("Submission/trained_submissions.csv")
    print trained_models
    l1 = leaderboard_classical(trained_models)
    return leaderboard_to_html(l1)

@app.route("/add/", methods=["GET", "POST"])
def add_submodule():
    if request.method == "POST":
        Submodule.add(
                repo = repo,
                name = request.form["name"],
                path = request.form["name"],
                url = request.form["url"],
            )
        return redirect(url_for('list_submodules'))
    else:
        sub_form = """
                    <form method="post">
                        <label>name</label>
                        <input type="text" name="name"/>
                        <label>git repository</label>
                        <input type="text" name="url"/>
                        <input type="submit" value="Add"/>
                    </form>
                   """
        return sub_form

if __name__ == "__main__":
    app.run(debug=False, port=8080)#, host='0.0.0.0')
    print list_submodules()
