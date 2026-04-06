@echo off
echo ====================================
echo  ARGOS: установка поисковых пакетов
echo ====================================
pip install "ddgs>=7.0.0" --quiet
pip install "duckduckgo-search>=6.0.0" --quiet
pip install "requests>=2.31.0" --quiet
echo.
echo Проверка...
python -c "try:
    from ddgs import DDGS
    print('OK: ddgs')
except:
    from duckduckgo_search import DDGS
    print('OK: duckduckgo_search (fallback)')"
echo.
echo Готово! Перезапусти ARGOS.
pause
