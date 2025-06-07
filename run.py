import uvicorn

if __name__ == "__main__":
    print("Starting server...")
    # 我们告诉Uvicorn，应用实例'app'在'backend/app/main.py'文件中
    # reload=True 会在代码变动时自动重启服务，方便开发
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True) 