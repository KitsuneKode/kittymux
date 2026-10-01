# kittymux — click a file reference (src/app.py:42 or src/app.py:42:7 in an agent's output or a
# compiler error) to open it in $VISUAL/$EDITOR at that line. kitty ≥ 0.49.2 detects these via
# detect_url_regex (kittymux turns that on); the click lands here. Linked to
# ~/.config/kitty/open-actions.conf by install.sh when you have none; otherwise copy the two lines below.
url ^[\w./~-]+\.\w+:\d+(:\d+)?$
action launch --type=window --cwd=current @KITTYMUX_HOME@/bin/mux-open-ref ${URL}
