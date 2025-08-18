import os
import io
import time
import re
import threading
import numpy as np
from collections import Counter, defaultdict
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, send_file, session, jsonify
from wordcloud import WordCloud, STOPWORDS
import pymorphy3
from PIL import Image, ImageDraw
import random
from stop_words import get_stop_words
import matplotlib.colors as mcolors

# Инициализация Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key')
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 6  # 6 часов

# Инициализация морфологического анализатора
morph = pymorphy3.MorphAnalyzer()

# Функция для нормализации слов
def normalize_word(word):
    word = word.lower().strip()
    word = re.sub(r'[^\w\s\'-]', '', word)
    parsed = morph.parse(word)[0]
    return parsed.normal_form

# Потокобезопасное хранилище
class GlobalStorage:
    def __init__(self):
        self.all_words = []
        self.lock = threading.Lock()
        self.word_counter = 0
    
    def add_word(self, user_id, word):
        normalized = normalize_word(word)
        with self.lock:
            self.all_words.append({
                "id": self.word_counter,
                "raw": word,
                "normalized": normalized,
                "user_id": user_id,
                "timestamp": time.time()
            })
            self.word_counter += 1
    
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
    
    def remove_word_by_id(self, word_id):
        try:
            word_id = int(word_id)
        except ValueError:
            return False
        
        with self.lock:
            self.all_words = [w for w in self.all_words if w['id'] != word_id]
            return True
    
    def get_all_normalized_words(self):
        with self.lock:
            return [w['normalized'] for w in self.all_words]
    
    def get_user_words(self, user_id):
        with self.lock:
            return [
                w['raw'] for w in self.all_words 
                if w['user_id'] == user_id
            ]
    
    def get_all_words_with_info(self):
        with self.lock:
            return self.all_words.copy()
    
    def clear_all(self):
        with self.lock:
            self.all_words = []
            self.word_counter = 0

global_storage = GlobalStorage()

# Фильтр для форматирования времени
@app.template_filter('datetime')
def format_datetime(value):
    try:
        return datetime.fromtimestamp(value).strftime('%H:%M:%S')
    except:
        return "N/A"

# Маршруты
@app.route("/", methods=["GET", "POST"])
def index():
    if 'user_id' not in session:
        session['user_id'] = os.urandom(16).hex()
    
    user_id = session['user_id']
    
    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text:
            for word in text.split():
                if word.strip():
                    global_storage.add_word(user_id, word.strip())
        return redirect(url_for('index'))
    
    user_words = global_storage.get_user_words(user_id)
    return render_template("index.html", user_words=user_words, ts=int(time.time()))

@app.route("/global-cloud.png")
def global_cloud_image():
    all_words = global_storage.get_all_normalized_words()
    if not all_words:
        return "Нет слов для облака", 400
        
    def make_mask(width, height):
        img = Image.new('L', (width, height), 255)
        draw = ImageDraw.Draw(img)
        draw.ellipse([5,5, width-5, height-5], fill=0)
        return np.array(img)

    
    russian_stopwords = set(get_stop_words('russian')) | {
        'это', 'как', 'так', 'и', 'в', 'над', 'к', 'до', 'не', 'на', 'но', 'за', 'то', 'с', 'ли',
        'а', 'во', 'от', 'со', 'для', 'о', 'же', 'ну', 'вы', 'бы', 'что', 'кто', 'он', 'она'
    }
    
    # Функция для градиентных цветов как на картинке (от зеленого к фиолетовому/голубому)
    def color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        hue = random.randint(30, 270)  # От желто-зеленого до фиолетового
        saturation = random.randint(50, 100)
        lightness = random.randint(30, 70)
        return f"hsl({hue}, {saturation}%, {lightness}%)"
    
    text = " ".join(all_words)
    wc = WordCloud(
        width=1400,
        height=800,
        background_color="#f0f8ff",  # Светло-голубой фон как на картинке
        collocations=False,
        stopwords=russian_stopwords,
        mask=make_mask(1400, 800),
        max_words=200,
        prefer_horizontal=0.7,  # Чуть больше вертикальных слов
        min_font_size=10,
        max_font_size=150,
        color_func=color_func,
        contour_width=0,  # Без контура для простоты
        random_state=42,  # Для воспроизводимости
        scale=2,
        relative_scaling=0.5,
    ).generate(text)

    img_io = io.BytesIO()
    wc.to_image().save(img_io, "PNG")
    img_io.seek(0)
    return send_file(img_io, mimetype="image/png")

@app.route("/word-frequencies")
def word_frequencies():
    all_words = global_storage.get_all_normalized_words()
    if not all_words:
        return jsonify([])
    
    word_counts = Counter(all_words)
    words_data = [{"text": word, "size": count} for word, count in word_counts.items()]
    return jsonify(words_data)

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

@app.route("/team-generator")
def team_generator():
    return render_template("team-generator.html")

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
    unique_words = set(all_words)
    return render_template(
        "admin.html",
        words_count=len(all_words),
        unique_words_count=len(unique_words),
        ts=int(time.time())
    )

@app.route("/admin/words")
def admin_words_panel():
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    if request.args.get('password') != admin_password:
        return "Неверный пароль", 403
    
    all_words = global_storage.get_all_words_with_info()
    return render_template(
        "admin-words.html",
        all_words=all_words,
        ts=int(time.time())
    )

@app.route("/admin/remove-word", methods=["POST"])
def admin_remove_word():
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    if request.form.get('password') != admin_password:
        return "Неверный пароль", 403
    
    word_id = request.form.get('word_id')
    if not word_id:
        return "Не указан ID слова", 400
    
    global_storage.remove_word_by_id(word_id)
    return jsonify(success=True)

@app.route("/clear-all")
def clear_all_words():
    admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
    if request.args.get('password') != admin_password:
        return "Неверный пароль", 403
    
    global_storage.clear_all()
    return redirect(url_for('admin_panel', password=request.args.get('password')))

@app.route("/display")
def display_fullscreen():
    return render_template("cloud-display.html", ts=int(time.time()))


# Добавить функции обработки фраз
def extract_keywords_from_text(text):
    """Извлечение ключевых слов из текста с нормализацией"""
    # Очистка текста
    text = text.lower().strip()
    
    # Удаление лишних символов, оставляем кириллицу, латиницу, цифры и пробелы
    text = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Разделение на слова
    words = text.split()
    
    # Фильтрация коротких слов и чисел
    words = [word for word in words if len(word) > 2 and not word.isdigit()]
    
    # Нормализация слов
    normalized_words = []
    for word in words:
        try:
            parsed = morph.parse(word)[0]
            normalized = parsed.normal_form
            # Фильтруем служебные части речи
            if parsed.tag.POS not in ['PREP', 'CONJ', 'PRCL', 'INTJ']:  # предлоги, союзы, частицы, междометия
                normalized_words.append(normalized)
        except:
            # Если не удалось нормализовать, добавляем как есть
            normalized_words.append(word)
    
    return list(set(normalized_words))  # Убираем дубликаты

def extract_phrases(text, max_phrase_length=4):
    """Извлечение фраз из текста"""
    import nltk
    from nltk.util import ngrams
    
    # Очистка текста
    text = text.lower().strip()
    text = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Разделение на слова
    words = text.split()
    words = [word for word in words if len(word) > 2 and not word.isdigit()]
    
    # Извлечение n-грамм (фраз)
    phrases = []
    for n in range(2, min(max_phrase_length + 1, len(words) + 1)):
        n_grams = ngrams(words, n)
        for gram in n_grams:
            phrase = ' '.join(gram)
            if len(phrase.split()) >= 2:  # Только фразы из 2+ слов
                phrases.append(phrase)
    
    return phrases

# Добавить маршрут для обработки фраз
@app.route("/process-phrase", methods=["POST"])
def process_phrase():
    if 'user_id' not in session:
        return jsonify(success=False, error="No session"), 401
    
    user_id = session['user_id']
    phrase = request.form.get("phrase", "").strip()
    
    if not phrase:
        return jsonify(success=False, error="Empty phrase"), 400
    
    # Извлекаем ключевые слова
    keywords = extract_keywords_from_text(phrase)
    
    # Добавляем нормализованные слова
    added_words = []
    for keyword in keywords:
        if keyword.strip():
            global_storage.add_word(user_id, keyword.strip())
            added_words.append(keyword.strip())
    
    return jsonify({
        'success': True,
        'added_words': added_words,
        'count': len(added_words)
    })

# Альтернативный метод - извлечение фраз
@app.route("/extract-phrases", methods=["POST"])
def extract_phrases_route():
    if 'user_id' not in session:
        return jsonify(success=False, error="No session"), 401
    
    user_id = session['user_id']
    text = request.form.get("text", "").strip()
    
    if not text:
        return jsonify(success=False, error="Empty text"), 400
    
    # Извлекаем фразы
    phrases = extract_phrases(text)
    
    # Для каждой фразы извлекаем ключевые слова
    all_keywords = []
    for phrase in phrases[:10]:  # Ограничиваем 10 фразами
        keywords = extract_keywords_from_text(phrase)
        all_keywords.extend(keywords)
    
    # Убираем дубликаты
    unique_keywords = list(set(all_keywords))
    
    # Добавляем в хранилище
    added_words = []
    for keyword in unique_keywords:
        if keyword.strip():
            global_storage.add_word(user_id, keyword.strip())
            added_words.append(keyword.strip())
    
    return jsonify({
        'success': True,
        'added_words': added_words,
        'count': len(added_words),
        'phrases_found': len(phrases)
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
