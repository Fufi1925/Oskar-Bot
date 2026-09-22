import uvicorn
from lbost_shop_app.config import get_settings

if __name__ == "__main__":
    uvicorn.run("lbost_shop_app.main:app", host="0.0.0.0", port=8790, reload=False)
