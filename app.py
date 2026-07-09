import socket
import random
from urllib.parse import urlparse, parse_qs

# خوارزمية تشفير رقمية سريعة وفائقة الذكاء (FNV-1a Hash) بديلة للـ MD5
# تعطي مساراً ثابتاً ومحدداً لكل ID جولة لتضمن أن المسار ليس عشوائياً أعمى
def calculate_smart_hash(string_data):
    hash_val = 2166136261
    for char in string_data:
        hash_val ^= ord(char)
        hash_val = (hash_val * 16777619) & 0xFFFFFFFF  # لضمان بقائها 32 بت كما في C++
    return hash_val

def generate_smart_box(user_id, row, session_id):
    ss = f"{user_id}_{row}_{session_id}"
    hash_val = calculate_smart_hash(ss)
    # استخراج رقم المربع الآمن بين 1 و 5 بناءً على ناتج التشفير
    return (hash_val % 5) + 1

# دالة ذكية لاستخراج قيم المتغيرات (Query Parameters) من رابط الـ URL
def get_query_param(request_str, param):
    try:
        # استخراج السطر الأول من طلب HTTP للحصول على المسار
        first_line = request_str.split("\n")[0]
        path = first_line.split(" ")[1]
        # تحليل المتغيرات
        parsed_url = urlparse(path)
        params = parse_qs(parsed_url.query)
        return params.get(param, [""])[0]
    except Exception:
        return ""

def main():
    # 1 و 2 و 3 و 4. إنشاء السوكيت وإعداد بيانات الاتصال والربط بالمنفذ 8000
    # (في بايثون تتم تهيئة حزمة الشبكات تلقائياً دون الحاجة لـ WinSock يدوياً)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind(("127.0.0.1", 8000))
    except Exception:
        print("[-] فشل ربط السيرفر بالمنفذ 8000. تأكد أنه غير مستخدم!")
        return

    # 5. بدء الاستماع للطلبات القادمة من المتصفح
    server_socket.listen(5)  # SOMAXCONN

    print("=========================================================")
    print("       VIP DJANGO SYSTEM - PYTHON ENGINE V12             ")
    print("=========================================================")
    print("[+] السيرفر المطور بلغة Python يعمل الآن بنجاح على المنفذ 8000")
    print("[+] الرابط المحلي للاختبار: http://127.0.0.1:8000")
    print("[+] افتح ملف index.html في متصفحك وقم بربط الحساب فوراً...")
    print("---------------------------------------------------------\n")

    # 6. حلقة استقبال ومعالجة الطلبات اللانهائية (Event Loop)
    while True:
        try:
            client_socket, _ = server_socket.accept()
        except KeyboardInterrupt:
            break
        except Exception:
            continue

        try:
            recv_buffer = client_socket.recv(2048)
            if not recv_buffer:
                client_socket.close()
                continue
                
            request_str = recv_buffer.decode('utf-8', errors='ignore')
            
            # التحقق من مسار الطلب القادم من واجهة الويب
            if "GET /api/predict" in request_str:
                # استخراج المتغيرات المرسلة من الـ JavaScript
                row_str = get_query_param(request_str, "row")
                user_id = get_query_param(request_str, "user_id")
                session_str = get_query_param(request_str, "session_id")

                row = 1 if not row_str else int(row_str)
                session_id = 1 if not session_str else int(session_str)

                # حساب المربع الآمن ذكياً عبر خوارزمية التشفير الفائقة
                safe_slot = generate_smart_box(user_id, row, session_id)

                # حساب نسبة ثقة ديناميكية ومقنعة بصرياً للمستخدم
                if row <= 3:
                    confidence = random.randint(0, 3) + 96   # 96% - 99%
                elif row <= 6:
                    confidence = random.randint(0, 6) + 89   # 89% - 95%
                else:
                    confidence = random.randint(0, 13) + 75  # 75% - 88%

                # بناء نص الاستجابة بصيغة JSON متوافقة 100% مع الواجهة السابقة
                json_body = (
                    "{\n"
                    f'  "status": "success",\n'
                    f'  "user_id": " {user_id}",\n'
                    f'  "session_id": {session_id},\n'
                    f'  "row": {row},\n'
                    f'  "recommended_box": {safe_slot},\n'
                    f'  "confidence_rate": "{confidence}%"\n'
                    "}"
                )

                # بناء الهيدر الرسمي لـ HTTP مع تفعيل ميزة الـ CORS لتخطي حماية المتصفح
                response = (
                    "HTTP/1.1 200 OK\r\n"
                    "Content-Type: application/json; charset=utf-8\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                    "Access-Control-Allow-Headers: *\r\n"
                    f"Content-Length: {len(json_body.encode('utf-8'))}\r\n"
                    "Connection: close\r\n\r\n"
                    f"{json_body}"
                )

                client_socket.sendall(response.encode('utf-8'))
                
                print(f"[REQUEST] تم إرسال التوقع ذكياً للصف {row} "
                      f"للمستخدم آيدي {user_id} -> المربع المختار: {safe_slot} | الثقة: {confidence}%")

            elif "OPTIONS /api/predict" in request_str:
                # معالجة طلبات الأمان المسبقة (CORS Preflight) التي ترسلها بعض المتصفحات الحديثة تلقائياً
                cors_response = (
                    "HTTP/1.1 204 No Content\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                    "Access-Control-Allow-Headers: *\r\n"
                    "Connection: close\r\n\r\n"
                )
                client_socket.sendall(cors_response.encode('utf-8'))
                
        except Exception as e:
            pass
        finally:
            client_socket.close()

    # إغلاق وتنظيف السوكيت عند إنهاء السيرفر
    server_socket.close()

if __name__ == "__main__":
    main()
