import redis
r = redis.Redis()
r.mset({"Croatia": "Zagreb", "Bahamas":"Nassau"})
out = r.get("Bahamas").decode("utf-8")
print(out)