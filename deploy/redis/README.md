# bookademy-redis

The Celery broker, deployed from the stock `redis:7-alpine` image with a 1GB volume
for its append-only file.

```
fly deploy -c deploy/redis/fly.toml -a bookademy-redis
```

It is reachable only from inside the Fly organisation, at
`redis://bookademy-redis.flycast:6379/0`. There is no public port and no password,
which is safe only because of that — `.flycast` addresses are not routable from the
internet.
