import os
import io
import time
import threading
from flask import Flask, render_template, request, redirect, url_for, send_file, session

# Для генерации облака слов
from wordcloud import WordCloud, STOPWORDS

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key')

# Потокобезопасное хранилище для всех слов
class GlobalStorage:
    def __init__(self):
        self.all_words = []
        self.lock = threading.Lock()
    
    def add_word(self, word):
        with self.lock:
            self.all_words.append(word)
    
    def clear_all(self):
        with self.lock:
            self.all_words = []
    
    def get_all_words(self):
        with self.lock:
            return self.all_words.copy()

global_storage = GlobalStorage()

@app.route("/", methods=["GET", "POST"])
def index():
    # Инициализация сессии пользователя
    if 'user_words' not in session:
        session['user_words'] = []
    
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text:
            # Добавляем слово в личный список пользователя
            session['user_words'].append(text)
            session.modified = True
            
            # Добавляем слово в глобальную копилку
            global_storage.add_word(text)
            
        return redirect(url_for('index'))
    
    return render_template(
        "index.html",
        user_words=session.get('user_words', []),
        ts=int(time.time())
    )

@app.route("/user-cloud.png")
def user_cloud_image():
    user_words = session.get('user_words', [])
    if not user_words:
        return "Нет слов для облака", 400
    
    return generate_wordcloud_image(" ".join(user_words))

@app.route("/global-cloud.png")
def global_cloud_image():
    all_words = global_storage.get_all_words()
    if not all_words:
        return "Нет слов для облака", 400
    
    return generate_wordcloud_image(" ".join(all_words))

def generate_wordcloud_image(text):
    # Генерация облака слов
    wc = WordCloud(
        width=1200,
        height=600,
        background_color="white",
        collocations=False,
        stopwords=STOPWORDS,
        max_words=200,
        prefer_horizontal=0.9,
        min_font_size=10,
        contour_width=3,
        contour_color='steelblue'
    ).generate(text)

    img_io = io.BytesIO()
    wc.to_image().save(img_io, "PNG")
    img_io.seek(0)
    return send_file(img_io, mimetype="image/png")

@app.route("/clear-user")
def clear_user_words():
    # Очищаем только слова текущего пользователя
    if 'user_words' in session:
        session.pop('user_words')
        session.modified = True
    return redirect(url_for('index'))

@app.route("/admin")
def admin_panel():
    # Простая защита паролем
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    if request.args.get('password') != admin_password:
        return "Неверный пароль", 403
    
    all_words = global_storage.get_all_words()
    return render_template(
        "admin.html",
        all_words=all_words,
        words_count=len(all_words),
        ts=int(time.time())
    )

@app.route("/clear-all")
def clear_all_words():
    # Очищаем все слова
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    if request.args.get('password') != admin_password:
        return "Неверный пароль", 403
    
    global_storage.clear_all()
    return redirect(url_for('admin_panel', password=request.args.get('password')))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
