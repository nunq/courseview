# courseview

visualize available courses in a weekly calender view, desktop screen required

link: https://nunq.github.io/courseview/

<img src="./screenshot.png"/>

## features
- persists the selected courses in browser's localstorage
- search across available courses
- customize each course's colors
- clicking on an event in the calendar highlights it in the course list
- add your own custom events into the schedule (also persisted)
- export the selected courses as an `ics` file which can be imported into any calendar
- get suggestions on which days to go to work instead of uni (brute forces the minimum number of conflicts with the selected courses)
- for zoom, just use your browser's zoom `ctrl +`

## local setup

- get your `inf-bachelor.html` / `inf-master.html`
- `python parse.py -i input.html -o datasets/courses_(ba|ma)_(ss|ws)YY.json`
- add it to the manifests file `datasets/manifest.json`
- `python -m http.server 8000 -b 127.0.0.1`

---

note: this code was fully generated using llms
