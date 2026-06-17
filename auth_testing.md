# Auth-Gated App Testing Playbook (Fut Connect)

## Step 1: Create Test User & Session
```bash
mongosh --eval "
use('test_database');
var userId = 'test-user-' + Date.now();
var sessionToken = 'test_session_' + Date.now();
db.users.insertOne({
  user_id: userId,
  email: 'test.atleta.' + Date.now() + '@example.com',
  name: 'Atleta Teste',
  picture: 'https://via.placeholder.com/150',
  role: 'atleta',
  created_at: new Date()
});
db.user_sessions.insertOne({
  user_id: userId,
  session_token: sessionToken,
  expires_at: new Date(Date.now() + 7*24*60*60*1000),
  created_at: new Date()
});
print('Session token: ' + sessionToken);
print('User ID: ' + userId);
"
```

## Step 2: Browser Testing
```js
await page.context.add_cookies([{
  "name": "session_token",
  "value": "YOUR_SESSION_TOKEN",
  "domain": "your-app.com",
  "path": "/",
  "httpOnly": true,
  "secure": true,
  "sameSite": "None"
}]);
await page.goto("https://your-app.com/dashboard");
```

## Checklist
- User document has `user_id` (custom UUID)
- Session `user_id` matches user's `user_id`
- All queries use `{"_id": 0}` projection
- `/api/auth/me` returns user data, dashboard loads without redirect
