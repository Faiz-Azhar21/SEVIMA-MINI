# UML Sequence Diagram & Class Diagram — Observer Pattern + Transactional Outbox

Dokumen ini memvisualisasikan alur eksekusi **aktual** pada codebase SEVIMA-Mini
([service.py](../app/scheduling/service.py),
[outbox.py](../app/scheduling/outbox.py),
[observer.py](../app/scheduling/observer.py), dan
[invalidator.py](../app/krs/invalidator.py)).

> **Poin Kritis Audit Arsitektur:** Perhatikan bahwa perintah `COMMIT` berada **di atas** (sebelum) `OutboxDispatcher` memanggil `ScheduleSubject.notify(event)`. Dengan demikian, notifikasi tidak pernah dikirim untuk perubahan jadwal yang gagal/di-rollback.

---

## 1. UML Sequence Diagram — Update Jadwal, Invalidasi KRS, Outbox, & Notifikasi

```mermaid
sequenceDiagram
    actor Admin as Admin Akademik
    participant API as FastAPI Router
    participant Service as SchedulingService
    participant KRSInv as KRSInvalidator
    participant DB as Database (SQLAlchemy)
    participant Disp as OutboxDispatcher
    participant Subject as ScheduleSubject
    participant Obs as Observer (Student/Lecturer/Admin)
    participant Chan as LogChannel (EMAIL/SMS/PUSH)

    Admin->>API: PUT /api/jadwal/{id} atau POST /api/jadwal/{id}/apply
    API->>Service: update(jadwal_id, data)
    Service->>DB: SELECT Ruangan & Dosen FOR UPDATE (lock)
    Service->>DB: Cek bentrok (detect_schedule_conflict) & cek_kapasitas
    alt Bentrok atau kapasitas tidak cukup
        Service->>DB: ROLLBACK
        Service-->>API: raise ScheduleConflictError / CapacityExceededError
        API-->>Admin: 409 Conflict
    else Valid
        Service->>Service: Salin field baru & naikkan jadwal.sequence += 1
        Service->>KRSInv: invalidate(kelas_id, "Jadwal berubah")
        KRSInv->>DB: SELECT KRS (SUBMITTED/APPROVED) FOR UPDATE
        KRSInv->>KRSInv: krs.transition(REVISION, Actor.SISTEM)
        Service->>DB: UPDATE jadwal + UPDATE krs + INSERT outbox (PENDING)
        Service->>DB: COMMIT
        DB-->>Service: OK (1 transaksi atomik selesai)

        Service->>Disp: run() (setelah COMMIT)
        Disp->>DB: SELECT outbox WHERE status='PENDING' FOR UPDATE SKIP LOCKED
        DB-->>Disp: baris outbox
        Disp->>Subject: notify(row.ke_event())
        loop Setiap observer (salinan list, dibungkus try/except)
            Subject->>Obs: update(event)
            loop Setiap kanal (EMAIL, SMS, PUSH)
                Obs->>Chan: send(penerima, pesan, idempotency_key)
                Chan->>Chan: Cek IdemStore.sudah(key)
                alt Belum pernah terkirim
                    Chan->>Chan: log.info("[CHANNEL] ...") & IdemStore.catat(key)
                else Duplikat saat retry
                    Chan->>Chan: Abaikan (deduplikasi)
                end
            end
        end
        Subject-->>Disp: daftar observer gagal (kosong jika semua sukses)
        Disp->>DB: UPDATE outbox SET status='SENT' (atau tetap PENDING / FAILED jika attempts>=5)
        Disp->>DB: COMMIT
        Service-->>API: Jadwal terbarui
        API-->>Admin: 200 OK
    end
```

---

## 2. UML Class Diagram — Observer Pattern & Strategy Channel

```mermaid
classDiagram
    class ScheduleSubject {
        -_observers: list~Observer~
        +attach(observer: Observer) None
        +detach(observer: Observer) None
        +notify(event: ScheduleEvent) list~str~
    }

    class Observer {
        <<Protocol>>
        +update(event: ScheduleEvent) None
    }

    class ScheduleEvent {
        <<frozen dataclass>>
        +event_type: EventType
        +jadwal_id: int
        +before: dict | None
        +after: dict | None
        +event_id: str
    }

    class StudentObserver {
        -peserta: PesertaRepo
        -channels: list~Channel~
        +update(event: ScheduleEvent) None
    }

    class LecturerObserver {
        -dosen_repo: DosenRepo
        -channels: list~Channel~
        +update(event: ScheduleEvent) None
    }

    class AdminObserver {
        -admin_kontak: str
        -channels: list~Channel~
        +update(event: ScheduleEvent) None
    }

    class Channel {
        <<Protocol>>
        +nama: str
        +send(penerima: str, pesan: str, key: str) None
    }

    class LogChannel {
        +nama: str
        -store: IdemStore
        +send(penerima: str, pesan: str, key: str) None
    }

    ScheduleSubject o--> Observer : memberitahu
    ScheduleSubject ..> ScheduleEvent : mempublikasikan
    Observer <|.. StudentObserver
    Observer <|.. LecturerObserver
    Observer <|.. AdminObserver
    StudentObserver --> Channel : memakai
    LecturerObserver --> Channel : memakai
    AdminObserver --> Channel : memakai
    Channel <|.. LogChannel
```
