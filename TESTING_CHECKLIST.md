# 🧪 Testing Checklist - AI Appointment Setter

قائمة اختبار شاملة لجميع ميزات النظام قبل الإطلاق.

---

## ✅ 1. WhatsApp Integration

### A. Send Test Messages
- [ ] Template: `hello_world` (no variables)
  - [ ] Status: PENDING → QUEUED → SENT → DELIVERED
  - [ ] Message received on phone
- [ ] Template: `greet` (with variables)
  - [ ] Variables: `{"first_name":"Ahmad"}`
  - [ ] Status: PENDING → QUEUED → SENT → DELIVERED
  - [ ] Message received with correct variable substitution
- [ ] Template: `confirm_booking` (if exists)
  - [ ] Test with all required variables
  - [ ] Verify message format

### B. Create New Template
- [ ] Create template in Meta Business Manager
  - [ ] Name: `appointment_confirmation`
  - [ ] Language: `English`
  - [ ] Variables: `{{patient_name}}, {{date}}, {{time}}`
  - [ ] Status: APPROVED
- [ ] Add template in system (`/templates` page)
  - [ ] Use Add Template button
  - [ ] Fill all fields correctly
  - [ ] Verify it appears in list
- [ ] Test sending new template
  - [ ] From Integrations page
  - [ ] Verify message delivery

### C. Template Management UI
- [ ] Preview all templates
  - [ ] Verify variables show as `[variable_name]`
  - [ ] No LINT_FAILED errors
- [ ] Filter by language
  - [ ] All Languages
  - [ ] Arabic
  - [ ] English
  - [ ] English (US)
- [ ] Enable/Disable templates
  - [ ] Toggle status
  - [ ] Verify status updates
- [ ] Language column displays correctly
  - [ ] Arabic → Amber badge
  - [ ] English → Green badge
  - [ ] English (US) → Blue badge

### D. WhatsApp Channel Configuration
- [ ] Update WhatsApp Channel settings
  - [ ] Form pre-populates with existing data
  - [ ] Access Token hidden (shows dots)
  - [ ] Can update individual fields
  - [ ] Phone Number ID displayed
- [ ] Test with expired token
  - [ ] Get new token from Meta
  - [ ] Update via UI
  - [ ] Verify new token works

---

## ✅ 2. Google Calendar Integration

### A. OAuth Setup
- [ ] Google Calendar connected
  - [ ] Status shows "Connected"
  - [ ] Calendar email displayed
- [ ] Disconnect/Reconnect
  - [ ] Can disconnect calendar
  - [ ] Can reconnect with OAuth flow

### B. Appointment Creation
- [ ] Create new appointment
  - [ ] Select/create patient
  - [ ] Select service
  - [ ] Choose date & time
  - [ ] Add notes (optional)
  - [ ] Book appointment
- [ ] Verify in system
  - [ ] Appears in Appointments list
  - [ ] Status: CONFIRMED
  - [ ] Event ID saved in database
- [ ] Verify in Google Calendar
  - [ ] Event appears in calendar
  - [ ] Correct date & time
  - [ ] Correct title & description
  - [ ] Attendee email (if provided)

### C. Appointment Modification
- [ ] Edit appointment
  - [ ] Change time
  - [ ] Change service
  - [ ] Update notes
  - [ ] Save changes
- [ ] Verify in Google Calendar
  - [ ] Changes reflected
  - [ ] Event ID unchanged

### D. Appointment Cancellation
- [ ] Cancel appointment
  - [ ] From Appointments page
  - [ ] Confirm cancellation
- [ ] Verify in Google Calendar
  - [ ] Event deleted or cancelled
- [ ] Verify in system
  - [ ] Status: CANCELLED

---

## ✅ 3. Complete End-to-End Flow

### Scenario: Patient Books Appointment via WhatsApp

**Step 1: Patient Initiates Contact**
- [ ] Patient sends message to WhatsApp Business number
  - Example: "السلام عليكم، أريد حجز موعد"
- [ ] System receives message (check webhook logs)
  - `docker compose logs web | grep webhook`
- [ ] Message saved in database
  - Check `ConversationMessage` table

**Step 2: System Responds**
- [ ] System sends greeting template
  - Template: `greet`
  - Variables filled correctly
- [ ] Patient receives message on WhatsApp

**Step 3: Admin Books Appointment**
- [ ] Admin opens Appointments page
- [ ] Creates appointment for patient
  - Links to existing patient or creates new
  - Selects service
  - Chooses available slot
- [ ] Appointment saved successfully

**Step 4: Calendar Integration**
- [ ] Appointment appears in Google Calendar
  - Correct time & date
  - Correct title
- [ ] Event ID saved in database

**Step 5: Confirmation Message**
- [ ] System sends confirmation template
  - Template: `appointment_confirmation`
  - Variables: patient name, date, time
- [ ] Patient receives confirmation on WhatsApp

**Step 6: Reminder (24 hours before)**
- [ ] System sends reminder automatically
  - Check Celery Beat logs
  - Verify task scheduled
- [ ] Patient receives reminder message

---

## ✅ 4. Webhook Integration

### A. Inbound Messages
- [ ] Configure webhook in Meta Business Manager
  - Callback URL: `https://your-domain.com/webhook/whatsapp`
  - OR (for testing): `https://your-ngrok-url.ngrok.io/webhook/whatsapp`
  - Verify Token: matches `.env` value
  - Subscriptions: `messages`, `message_status`
- [ ] Test receiving messages
  - Send message from personal phone
  - Check logs: `docker compose logs web | grep webhook`
  - Verify message in database

### B. Delivery Receipts
- [ ] Send test message from system
- [ ] Verify status updates:
  - SENT → DELIVERED → READ (if applicable)
- [ ] Check webhook receives status updates

---

## ✅ 5. Multi-Language Support

### A. Arabic Templates
- [ ] Create Arabic template in Meta
  - Language: `ar` (Arabic)
  - Status: APPROVED
- [ ] Add to system with language: `Arabic`
- [ ] Test sending Arabic message
  - Verify correct RTL display
  - Verify variables substitution

### B. English Templates
- [ ] Templates with language: `en`
  - Match Meta exactly
- [ ] Templates with language: `en_US`
  - Match Meta exactly
- [ ] Test both variations

---

## ✅ 6. Background Jobs (Celery)

### A. Worker Status
- [ ] Worker is running
  - `docker compose ps` shows worker UP
  - No restart loops
- [ ] Worker processes messages
  - Check logs: `docker compose logs worker --tail 50`
  - Messages dispatched within 10 seconds

### B. Beat Status
- [ ] Beat is running
  - `docker compose ps` shows beat UP
  - No errors in logs
- [ ] Scheduled tasks execute
  - `dispatch_outbox_messages` runs every 10s
  - Check logs: `docker compose logs beat --tail 50`

### C. Message Processing
- [ ] PENDING messages become QUEUED
  - Check message status in Integrations
- [ ] QUEUED messages become SENT
  - Within 10 seconds
- [ ] SENT messages become DELIVERED
  - When webhook confirms delivery

---

## ✅ 7. Error Handling

### A. Invalid Template
- [ ] Try sending template with wrong variables
  - Should return LINT_FAILED
  - Error message displayed

### B. Expired Access Token
- [ ] Let token expire
  - System returns clear error
  - Admin can update token via UI

### C. Network Issues
- [ ] Simulate network failure (disconnect)
  - Messages remain in QUEUED
  - Retry when connection restored

---

## ✅ 8. Performance & Reliability

### A. System Health
- [ ] All services running
  - `docker compose ps` - all UP
  - No restart loops
- [ ] Database healthy
  - Queries execute quickly
  - No connection errors
- [ ] Redis healthy
  - Celery tasks queued properly

### B. Logs Review
- [ ] Web logs clean
  - `docker compose logs web --tail 100`
  - No critical errors
- [ ] Worker logs clean
  - `docker compose logs worker --tail 100`
  - Tasks completing successfully
- [ ] Beat logs clean
  - `docker compose logs beat --tail 100`
  - Schedule tasks running

### C. Response Times
- [ ] UI loads quickly (< 2s)
- [ ] API responses fast (< 500ms)
- [ ] Messages sent within 10s

---

## ✅ 9. Security Checks

### A. Authentication
- [ ] Login required for all pages
- [ ] Session timeout works
- [ ] Logout works correctly

### B. API Security
- [ ] Webhook signature verification
  - Meta webhook validates correctly
- [ ] API endpoints require auth
  - Cannot access without session

### C. Environment Variables
- [ ] All secrets in `.env`
- [ ] `.env` not committed to git
- [ ] Production values differ from dev

---

## ✅ 10. Documentation

- [ ] `TESTING_GUIDE.md` up to date
  - Reflects current system state
  - Clear instructions for setup
- [ ] `README.md` accurate
  - Installation steps work
  - Dependencies listed correctly
- [ ] Environment variables documented
  - `.env.example` complete
  - All variables explained

---

## 🎯 Priority Testing Order

### **Critical (Test Now):**
1. WhatsApp send test (hello_world, greet)
2. Google Calendar appointment creation
3. Template Preview functionality
4. WhatsApp configuration UI

### **Important (Test Soon):**
5. Create new template flow
6. Complete end-to-end appointment flow
7. Webhook inbound messages
8. Multi-language templates

### **Nice to Have (Test Before Launch):**
9. Reminder messages
10. Error handling scenarios
11. Performance testing
12. Security review

---

## 📊 Progress Tracking

- **Completed:** 0 / 80 tests
- **In Progress:** 0 tests
- **Blocked:** 0 tests
- **Last Updated:** 2025-12-07

---

## 🚀 Ready for Launch Criteria

- [ ] All Critical tests passing (100%)
- [ ] All Important tests passing (100%)
- [ ] At least 80% of Nice to Have tests passing
- [ ] No critical errors in logs
- [ ] All services stable for 24+ hours
- [ ] Documentation complete and accurate

---

**Notes:**
- Mark completed items with `[x]`
- Add notes for blocked or failed tests
- Update progress tracking regularly

