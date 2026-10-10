import socket
import json
from urllib.parse import urlparse, parse_qs

import rounds_store

# --- المنطق الأصلي محفوظ للتوافق، لكن مصنف كتجريبي فقط ---
# كان يوصف سابقاً بأنه "ذكي/فائق الذكاء" — هذا الوصف أزيل لأنه مضلل.
# الدالة حتمية: نفس المدخلات تعطي نفس المخرجات، ولا تتصل بـ 1xBet.

def calculate_smart_hash(string_data):
    hash_val = 2166136261
    for char in string_data:
        hash_val ^= ord(char)
        hash_val = (hash_val * 16777619) & 0xFFFFFFFF
    return hash_val


def generate_smart_box(user_id, row, session_id):
    """توقع تجريبي محلي — ليس تنبؤاً بنتائج 1xBet الحقيقية."""
    ss = f"{user_id}_{row}_{session_id}"
    hash_val = calculate_smart_hash(ss)
    return (hash_val % 5) + 1


def get_query_param(request_str, param):
    try:
        first_line = request_str.split("\n")[0]
        path = first_line.split(" ")[1]
        parsed_url = urlparse(path)
        params = parse_qs(parsed_url.query)
        return params.get(param, [""])[0]
    except Exception:
        return ""


def get_path(request_str):
    try:
        first_line = request_str.split("\n")[0]
        raw_path = first_line.split(" ")[1]
        return urlparse(raw_path).path
    except Exception:
        return ""


def get_method(request_str):
    try:
        return request_str.split(" ")[0].strip().upper()
    except Exception:
        return ""


def send_json(client_socket, obj, status="200 OK"):
    body = json.dumps(obj, ensure_ascii=False)
    body_bytes = body.encode("utf-8")
    response = (
        f"HTTP/1.1 {status}\r\n"
        "Content-Type: application/json; charset=utf-8\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
        "Access-Control-Allow-Headers: *\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode("utf-8") + body_bytes
    client_socket.sendall(response)


def recv_full_request(client_socket):
    """يقرأ الهيدر ثم الجسم حسب Content-Length إن وجد."""
    data = b""
    client_socket.settimeout(3)
    try:
        chunk = client_socket.recv(8192)
    except Exception:
        return ""
    if not chunk:
        return ""
    data += chunk
    try:
        header_end = data.find(b"\r\n\r\n")
        if header_end != -1:
            header = data[:header_end].decode("utf-8", errors="ignore")
            content_len = 0
            for line in header.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    try:
                        content_len = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        content_len = 0
            body_already = len(data) - (header_end + 4)
            remaining = content_len - body_already
            while remaining > 0:
                try:
                    more = client_socket.recv(min(8192, remaining))
                except Exception:
                    break
                if not more:
                    break
                data += more
                remaining -= len(more)
    except Exception:
        pass
    return data.decode("utf-8", errors="ignore")


def extract_json_body(request_str):
    try:
        idx = request_str.find("\r\n\r\n")
        if idx == -1:
            return None
        body = request_str[idx + 4 :].strip()
        if not body:
            return None
        return json.loads(body)
    except Exception:
        return None


def main():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind(("127.0.0.1", 8000))
    except Exception:
        print("[-] bind failed on port 8000. Port may be in use!")
        return

    server_socket.listen(5)

    print("=========================================================")
    print("       BOTTOFFAHA - EXPERIMENTAL ENGINE V13              ")
    print("=========================================================")
    print("[+] experimental mode: no prediction of real 1xBet results.")
    print("[+] server on: http://127.0.0.1:8000")
    print("[+] endpoints: /api/predict , /api/rounds , /api/stats , /api/report , /api/export , /api/import")
    print("---------------------------------------------------------\n")

    while True:
        try:
            client_socket, _ = server_socket.accept()
        except KeyboardInterrupt:
            break
        except Exception:
            continue

        try:
            request_str = recv_full_request(client_socket)
            if not request_str:
                client_socket.close()
                continue

            method = get_method(request_str)
            path = get_path(request_str)

            if method == "OPTIONS" and path.startswith("/api/"):
                cors_response = (
                    "HTTP/1.1 204 No Content\r\n"
                    "Access-Control-Allow-Origin: *\r\n"
                    "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                    "Access-Control-Allow-Headers: *\r\n"
                    "Connection: close\r\n\r\n"
                )
                client_socket.sendall(cors_response.encode("utf-8"))

            elif method == "GET" and path == "/api/predict":
                row_str = get_query_param(request_str, "row")
                user_id = get_query_param(request_str, "user_id")
                session_str = get_query_param(request_str, "session_id")

                try:
                    row = 1 if not row_str else int(row_str)
                except ValueError:
                    row = 1
                try:
                    session_id = 1 if not session_str else int(session_str)
                except ValueError:
                    session_id = 1

                # تمت إزالة منطق الثقة الوهمية (random 96%-99% إلخ) نهائياً.
                # لا تولد تنبؤات مزعومة من نتائج لم تسجل — اقتراح تجريبي للمقارنة فقط.
                safe_slot = generate_smart_box(user_id, row, session_id)
                bcfg = rounds_store.get_baseline_config()

                send_json(
                    client_socket,
                    {
                        "status": "success",
                        "mode": "experimental",
                        "user_id": user_id,
                        "session_id": session_id,
                        "row": row,
                        "recommended_box": safe_slot,
                        "baseline_p": bcfg["baseline_p"],
                        "baseline_source": bcfg["source"],
                        "baseline_confirmed": bcfg["confirmed"],
                        "num_boxes": bcfg["num_boxes"],
                        "assumed_num_safe": bcfg["num_safe_per_row"],
                        "disclaimer": "توقع تجريبي محلي فقط — لا يعرف نتائج 1xBet القادمة. سجل النتيجة الفعلية بعد ظهورها. خط الأساس افتراض غير مؤكد حتى تثبت قواعد الطاولة.",
                    },
                )
                print(f"[PREDICT] row {row} user {user_id} -> experimental box: {safe_slot}")

            elif method == "POST" and path == "/api/rounds":
                payload = extract_json_body(request_str)
                if payload is None:
                    send_json(client_socket, {"status": "error", "message": "JSON body مطلوب"}, "400 Bad Request")
                else:
                    try:
                        saved = rounds_store.append_round(payload)
                        stats = rounds_store.compute_stats(rounds_store.load_rounds())
                        send_json(client_socket, {"status": "success", "round": saved, "stats_summary": {"total": stats["total"], "hit_rate": stats["hit_rate"]}})
                        print(f"[ROUND] saved: row {saved['row']} pred {saved['predicted_box']} actual {saved['actual_box']} -> {'HIT' if saved['hit'] else 'MISS'}")
                    except ValueError as ve:
                        send_json(client_socket, {"status": "error", "message": str(ve)}, "400 Bad Request")

            elif method == "GET" and path == "/api/rounds":
                limit_str = get_query_param(request_str, "limit")
                try:
                    limit = int(limit_str) if limit_str else 200
                except ValueError:
                    limit = 200
                rounds = rounds_store.load_rounds()
                send_json(client_socket, {"status": "success", "total": len(rounds), "rounds": rounds[-limit:]})

            elif method == "GET" and path == "/api/stats":
                rounds = rounds_store.load_rounds()
                bcfg = rounds_store.get_baseline_config()
                stats = rounds_store.compute_stats(rounds, baseline_p=bcfg["baseline_p"])
                # JSON لا يدعم مفاتيح int — نحول per_row لمفاتيح نصية
                stats["per_row"] = {str(k): v for k, v in stats["per_row"].items()}
                stats["baseline_source"] = bcfg["source"]
                stats["baseline_confirmed"] = bcfg["confirmed"]
                stats["num_boxes"] = bcfg["num_boxes"]
                stats["assumed_num_safe"] = bcfg["num_safe_per_row"]
                grouped = rounds_store.compute_grouped_stats(rounds)
                send_json(client_socket, {"status": "success", "stats": stats, "grouped": grouped})

            elif method == "GET" and path == "/api/report":
                bstr = get_query_param(request_str, "baseline_p")
                bcfg = rounds_store.get_baseline_config()
                try:
                    bp = float(bstr) if bstr else float(bcfg["baseline_p"])
                except ValueError:
                    bp = float(bcfg["baseline_p"])
                if not (0.0 < bp < 1.0):
                    send_json(client_socket, {"status": "error", "message": "baseline_p يجب أن يكون بين 0 و 1"}, "400 Bad Request")
                else:
                    rounds = rounds_store.load_rounds()
                    rep = rounds_store.build_report(rounds, baseline_p=bp)
                    send_json(client_socket, {"status": "success", "report": rep})

            elif method == "GET" and path == "/api/export":
                fmt = (get_query_param(request_str, "format") or "csv").lower()
                rounds = rounds_store.load_rounds()
                if fmt == "csv":
                    csv_text = rounds_store.export_csv(rounds)
                    body_bytes = csv_text.encode("utf-8")
                    head = (
                        "HTTP/1.1 200 OK\r\n"
                        "Content-Type: text/csv; charset=utf-8\r\n"
                        "Content-Disposition: attachment; filename=\"rounds.csv\"\r\n"
                        "Access-Control-Allow-Origin: *\r\n"
                        f"Content-Length: {len(body_bytes)}\r\n"
                        "Connection: close\r\n\r\n"
                    ).encode("utf-8") + body_bytes
                    client_socket.sendall(head)
                else:
                    send_json(client_socket, {"status": "success", "total": len(rounds), "rounds": rounds})

            elif method == "POST" and path == "/api/import":
                ctype = ""
                for line in request_str.split("\r\n"):
                    if line.lower().startswith("content-type:"):
                        ctype = line.split(":", 1)[1].strip().lower()
                        break
                if "text/csv" in ctype or "csv" in request_str.split("\r\n")[0]:
                    idx = request_str.find("\r\n\r\n")
                    raw_body = request_str[idx + 4 :] if idx != -1 else ""
                    parsed = rounds_store.import_csv(raw_body)
                    if parsed["imported"]:
                        res = rounds_store.append_many(parsed["rounds"])
                        send_json(client_socket, {"status": "success", "imported": res["appended"], "skipped": parsed["skipped"] + res["skipped"], "errors": (parsed["errors"] + res["errors"])[:20]})
                    else:
                        send_json(client_socket, {"status": "error", "message": "لا صفوف صالحة", "details": parsed["errors"][:20]}, "400 Bad Request")
                else:
                    payload = extract_json_body(request_str)
                    if payload is None:
                        send_json(client_socket, {"status": "error", "message": "أرسل CSV كنص أو JSON"}, "400 Bad Request")
                    elif isinstance(payload, list):
                        res = rounds_store.append_many(payload)
                        send_json(client_socket, {"status": "success", "imported": res["appended"], "skipped": res["skipped"], "errors": res["errors"][:20]})
                    elif isinstance(payload, dict) and isinstance(payload.get("rounds"), list):
                        res = rounds_store.append_many(payload["rounds"])
                        send_json(client_socket, {"status": "success", "imported": res["appended"], "skipped": res["skipped"], "errors": res["errors"][:20]})
                    else:
                        send_json(client_socket, {"status": "error", "message": "صيغة غير مدعومة: استخدم CSV أو قائمة rounds"}, "400 Bad Request")

            else:
                send_json(client_socket, {"status": "error", "message": "مسار غير معروف. استخدم /api/predict أو /api/rounds أو /api/stats أو /api/report أو /api/export أو /api/import"}, "404 Not Found")

        except Exception:
            try:
                send_json(client_socket, {"status": "error", "message": "خطأ داخلي"}, "500 Internal Server Error")
            except Exception:
                pass
        finally:
            client_socket.close()

    server_socket.close()


if __name__ == "__main__":
    main()
