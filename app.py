from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import psycopg2
from supabase import create_client, Client

# Flask 초기화
app = Flask(__name__)
CORS(app)

# 환경변수 불러오기
DATABASE_URL = os.getenv("DATABASE_URL")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ✅ DB 헬스체크
@app.route("/health/db")
def health_check():
    if supabase:
        try:
            res = supabase.table("attendees").select("*", count="exact").limit(1).execute()
            return jsonify({"db": "ok", "mode": "supabase-py", "rows": res.count})
        except Exception as e:
            return jsonify({"db": "error", "detail": str(e)})
    elif DATABASE_URL:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM attendees;")
            rows = cur.fetchone()[0]
            conn.close()
            return jsonify({"db": "ok", "mode": "psycopg2", "rows": rows})
        except Exception as e:
            return jsonify({"db": "error", "detail": str(e)})
    else:
        return jsonify({"db": "error", "detail": "No DB configured"})


# ✅ 온라인 체크인 API
@app.route("/checkin", methods=["POST"])
def checkin():
    try:
        data = request.get_json()
        student_id = data.get("student_id")

        if not student_id:
            return jsonify({"status": "error", "message": "학번이 필요합니다."}), 400

        # Supabase 모드
        if supabase:
            res = supabase.table("attendees").insert({
                "student_id": student_id
            }).execute()
            return jsonify({"status": "ok", "message": f"{student_id} 체크인 완료", "data": res.data})

        # PostgreSQL 모드
        elif DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("INSERT INTO attendees (student_id) VALUES (%s)", (student_id,))
            conn.commit()
            conn.close()
            return jsonify({"status": "ok", "message": f"{student_id} 체크인 완료"})

        else:
            return jsonify({"status": "error", "message": "DB 설정 없음"}), 500

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
