#!/bin/bash
# Script to create HQ staff user for local testing
# Usage: ./scripts/create_hq_user_local.sh [email] [password] [role]

set -e

EMAIL=${1:-"admin@test.com"}
PASSWORD=${2:-"Admin123!"}
ROLE=${3:-"SUPERADMIN"}

echo "Creating HQ staff user for local testing..."
echo "Email: $EMAIL"
echo "Role: $ROLE"
echo ""

docker-compose -f docker-compose.local.yml exec -T web python manage.py shell << EOF
from django.contrib.auth.models import User
from apps.accounts.models import StaffAccount

# Check if user exists
user = User.objects.filter(email="$EMAIL").first()
if user:
    print(f"User {user.email} already exists. Updating...")
    user.set_password("$PASSWORD")
    user.is_active = True
    user.save()
    
    # Update or create staff account
    staff, created = StaffAccount.objects.get_or_create(user=user)
    staff.role = StaffAccount.Role.$ROLE
    staff.save()
    
    if created:
        print(f"✅ Staff account created for {user.email}")
    else:
        print(f"✅ Staff account updated for {user.email}")
else:
    # Create new user
    user = User.objects.create_user(
        username="$EMAIL",
        email="$EMAIL",
        password="$PASSWORD",
        is_active=True
    )
    
    StaffAccount.objects.create(user=user, role=StaffAccount.Role.$ROLE)
    print(f"✅ HQ user created: $EMAIL")
    
print(f"✅ User ready: $EMAIL (Role: $ROLE)")
print(f"✅ Password: $PASSWORD")
EOF

echo ""
echo "✅ Done!"
echo ""
echo "You can now login at: http://localhost:3000/login"
echo "Email: $EMAIL"
echo "Password: $PASSWORD"

