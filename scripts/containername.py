import random
import string

print("".join(random.choice(string.ascii_lowercase) for i in range(32)))
