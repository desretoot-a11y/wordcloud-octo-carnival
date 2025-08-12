import os
import io
import time
from flask import Flask, render_template, request, redirect, url_for, send_file, session
from wordcloud import WordCloud

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key')

@app.route("/", methods=["GET", "POST"])
def index():
    # Инициализация списка слов в сессии
    if 'entries' not in session:
        session['entries'] = []
    
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text:
            # Добавляем слово в сессию пользователя
            session['entries'] = session.get('entries', []) + [text]
            session.modified = True  # Важно для сохранения изменений
        return redirect(url_for('index'))
    
    return render_template(
        "index.html",
        entries=session.get('entries', []),
        ts=int(time.time())
    )

@app.route("/cloud.png")
def cloud_image():
    entries = session.get('entries', [])
    if not entries:
        return "Нет слов для облака", 400
    
    full_text = " ".join(entries)
    wc = WordCloud(
        width=800,
        height=400,
        background_color="white",
        collocations=False
    ).generate(full_text)

    img_io = io.BytesIO()
    wc.to_image().save(img_io, "PNG")
    img_io.seek(0)
    return send_file(img_io, mimetype="image/png")

@app.route("/clear")
def clear():
    # Очищаем только слова текущего пользователя
    if 'entries' in session:
        session.pop('entries')
    return redirect(url_for('index'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
