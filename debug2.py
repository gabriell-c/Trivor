import os
print("CWD:", os.getcwd())
print("\nFiles in current dir:")
for f in os.listdir('.'):
    if f.endswith('.py') or f.endswith('.txt') or f.endswith('.json'):
        print(f"  {f}")

print("\nFiles in docs:")
for f in os.listdir('docs'):
    print(f"  {f}")
