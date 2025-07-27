
Я собирал эту программу в Windows 10. Версия Python 3.12.5.

Перед сборкой установите необходимые библиотеки. Запустите файл requirements.txt с помощью команды: pip install -r requirements.txt

Как получить bandicam.exe?

1. Запустите CMD (командная строка). 

2. Далее перейдите в папку, где находится bandicam.py (у меня это F:\PYTHON\bandicam)

cd /d F:\PYTHON\bandicam

3. Попробуйте запустить программу с помощью коммандной строки:

python bandicam.py

4.Что бы получить файл EXE введите следующую команду в коммандную строку:

pyinstaller --onefile --noconsole --icon=1.png bandicam.py

5. После сборки, в папке DIST вы найдете bandicam.exe
6. Добавлена кнопка скринота экрана и сохранение скриншота в файл .jpg
