import subprocess

def start_redis():
    try:
        # Starts a Redis server
        redis_process = subprocess.Popen(['redis-server', '--bind', '127.0.0.1', '--port', '6379'])
        print('Redis server started successfully.')
        return redis_process
    except Exception as e:
        print(f'Error starting Redis server: {e}')
        return None

if __name__ == "__main__":
    redis_process = start_redis()
