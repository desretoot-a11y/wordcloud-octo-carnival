import os
import io
import time
import threading
import re
from flask import Flask, render_template, request, redirect, url_for, send_file, session, jsonify
from wordcloud import WordCloud, STOPWORDS
import pymorphy3  # Для лемматизации русских слов

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key')

# Инициализация морфологического анализатора
morph = pymorphy3.MorphAnalyzer()

# Функция для нормализации слов
def normalize_word(word):
    # Приводим к нижнему регистру
    word = word.lower().strip()
    
    # Удаляем знаки препинания (кроме дефисов и апострофов)
    word = re.sub(r'[^\w\s\'-]', '', word)
    
    # Лемматизация
    parsed = morph.parse(word)[0]
    return parsed.normal_form

# Потокобезопасное хранилище
class GlobalStorage:
    def __init__(self):
        self.all_words = []
        self.lock = threading.Lock()
    
    def add_word(self, user_id, word):
        normalized = normalize_word(word)
        with self.lock:
            self.all_words.append({
                "raw": word,
                "normalized": normalized,
                "user_id": user_id
            })
    
    def remove_user_words(self, user_id):
        with self.lock:
            self.all_words = [w for w in self.all_words if w['user_id'] != user_id]
    
    def remove_word(self, user_id, word):
        normalized = normalize_word(word)
        with self.lock:
            self.all_words = [
                w for w in self.all_words 
                if not (w['user_id'] == user_id and w['normalized'] == normalized)
            ]
    
    def get_all_normalized_words(self):
        with self.lock:
            # Возвращаем только нормализованные слова
            return [w['normalized'] for w in self.all_words]
    
    def get_user_words(self, user_id):
        with self.lock:
            return [
                w['raw'] for w in self.all_words 
                if w['user_id'] == user_id
            ]
    
    def clear_all(self):
        with self.lock:
            self.all_words = []

global_storage = GlobalStorage()

@app.route("/", methods=["GET", "POST"])
def index():
    # Генерируем уникальный ID пользователя, если нет
    if 'user_id' not in session:
        session['user_id'] = os.urandom(16).hex()
    
    user_id = session['user_id']
    
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text:
            # Добавляем каждое слово отдельно
            for word in text.split():
                if word.strip():
                    global_storage.add_word(user_id, word.strip())
            
        return redirect(url_for('index'))
    
    # Получаем слова текущего пользователя
    user_words = global_storage.get_user_words(user_id)
    
    return render_template(
        "index.html",
        user_words=user_words,
        ts=int(time.time())
    )

@app.route("/global-cloud.png")
def global_cloud_image():
    all_words = global_storage.get_all_normalized_words()
    if not all_words:
        return "Нет слов для облака", 400
    
    # Фильтрация стоп-слов
    russian_stopwords = set(STOPWORDS) | {
        'это', 'как', 'так', 'и', 'в', 'над', 'к', 'до', 'не', 'на', 'но', 'за', 'то', 'с', 'ли',
        'а', 'во', 'от', 'со', 'для', 'о', 'же', 'ну', 'вы', 'бы', 'что', 'кто', 'он', 'она'
    }
    
    text = " ".join(all_words)
    wc = WordCloud(
        width=1200,
        height=600,
        background_color="white",
        collocations=False,
        stopwords=russian_stopwords,
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

@app.route("/remove-word", methods=["POST"])
def remove_word():
    if 'user_id' not in session:
        return jsonify(success=False), 401
    
    user_id = session['user_id']
    word = request.form.get("word")
    
    if not word:
        return jsonify(success=False), 400
    
    global_storage.remove_word(user_id, word)
    return jsonify(success=True)

@app.route("/clear-user")
def clear_user_words():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    user_id = session['user_id']
    global_storage.remove_user_words(user_id)
    return redirect(url_for('index'))

@app.route("/admin")
def admin_panel():
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    if request.args.get('password') != admin_password:
        return "Неверный пароль", 403
    
    all_words = global_storage.get_all_normalized_words()
    return render_template(
        "admin.html",
        words_count=len(all_words),
        unique_words_count=len(set(all_words)),
        ts=int(time.time())
    )

@app.route("/clear-all")
def clear_all_words():
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    if request.args.get('password') != admin_password:
        return "Неверный пароль", 403
    
    global_storage.clear_all()
    return redirect(url_for('admin_panel', password=request.args.get('password')))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
