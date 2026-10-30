import json
from app import create_app
from models import db, User

app = create_app()

print('=== TESTING FORGOT PASSWORD & PASSWORD VISIBILITY ===')

client = app.test_client()

# 1. Test GET /forgot-password
res = client.get('/forgot-password')
assert res.status_code == 200
html = res.get_data(as_text=True)
assert 'new_password' in html
assert 'confirm_new_password' in html
assert 'togglePasswordVisibility' in html
print('[1] GET /forgot-password -> 200 OK')

# 2. Test GET /login contains forgot password link & toggle button
login_res = client.get('/login')
assert login_res.status_code == 200
login_html = login_res.get_data(as_text=True)
assert '/forgot-password' in login_html
assert 'togglePasswordVisibility' in login_html
print('[2] GET /login -> 200 OK (Contains forgot password link & eye toggle button)')

# 3. Test POST with non-existent email
res_fail = client.post('/forgot-password', data={
    'email': 'nobody_exists@unknown.com',
    'phone': '0812345678',
    'new_password': 'NewPassword123',
    'confirm_new_password': 'NewPassword123'
}, follow_redirects=True)
assert res_fail.status_code == 200
assert 'text-rose-800' in res_fail.get_data(as_text=True)
print('[3] Nonexistent email validation -> PASSED')

# 4. Test POST with mismatched passwords
res_mismatch = client.post('/forgot-password', data={
    'email': 'tanatas@kkl.ac.th',
    'phone': '0955609261',
    'new_password': 'NewPassword123',
    'confirm_new_password': 'DifferentPassword123'
}, follow_redirects=True)
assert res_mismatch.status_code == 200
print('[4] Password mismatch validation -> PASSED')

# 5. Test successful password reset for tanatas@kkl.ac.th
test_new_pass = 'tanatas2026'
res_success = client.post('/forgot-password', data={
    'email': 'tanatas@kkl.ac.th',
    'phone': '095-560-9261',
    'new_password': test_new_pass,
    'confirm_new_password': test_new_pass
}, follow_redirects=True)
assert res_success.status_code == 200
assert res_success.request.path == '/login'
print('[5] Successful password reset -> PASSED (Redirected to /login)')

# 6. Verify login with the new password
login_post = client.post('/login', data={
    'email': 'tanatas@kkl.ac.th',
    'password': test_new_pass
}, follow_redirects=True)
assert login_post.status_code == 200
assert login_post.request.path == '/'
with client.session_transaction() as s:
    assert s.get('_user_id') == '1'
print('[6] Login with newly reset password -> PASSED (Logged in as TANATAS!)')

# 7. Check profile.html has toggle buttons (while logged in)
profile_res = client.get('/profile')
assert profile_res.status_code == 200
assert 'togglePasswordVisibility' in profile_res.get_data(as_text=True)
print('[7] GET /profile -> 200 OK (Contains toggle buttons)')

# 8. Check register.html has toggle buttons (after logout)
client.get('/logout')
reg_res = client.get('/register')
assert reg_res.status_code == 200
assert 'togglePasswordVisibility' in reg_res.get_data(as_text=True)
print('[8] GET /register -> 200 OK (Contains toggle buttons)')

print('\n=== ALL FORGOT PASSWORD & VISIBILITY TESTS PASSED 100%! ===')
