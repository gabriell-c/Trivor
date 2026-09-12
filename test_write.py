import os
with open("test_result.txt", "w") as f:
    f.write("Test passed\n")
    f.write(f"CWD: {os.getcwd()}\n")
    f.write(f"Files: {os.listdir('.')}")
print("Done")
