import bcrypt
password = "123456"  # замените на свой пароль
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
print(hashed.decode())