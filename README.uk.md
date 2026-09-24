# MagShift 🪄


**MagShift** виправляє текст, набраний не в тій розкладці, без повторного набору. Працює на Linux (Wayland та X11)
і macOS.

Набрали `ghbdsn` замість `привіт`? Натисніть **Shift** двічі: MagShift зітре фразу, перемкне розкладку і надрукує її
знову правильно. Ще раз двічі Shift повертає як було.

## Як це працює

MagShift слухає всі підключені клавіатури, зокрема під'єднані пізніше, і пам'ятає останню набрану фразу (до 20 клавіш;
пам'ять скидається після 1 секунди тиші, на `Enter`/`Tab`/`Esc` або після комбінацій на кшталт `Ctrl+C`). На подвійний
`Shift` він стирає фразу через `Backspace`, перемикає розкладку і набирає фразу знову. Буфер обміну не використовується,
нічого нікуди не надсилається.

🇬🇧 [Full documentation in English](./README.md)

## Встановлення

### NixOS (flake)

Додайте вхід `magshift.url = "github:OleksandrCEO/MagShift";`, імпортуйте модуль `magshift.nixosModules.default`,
додайте overlay (див. [повний приклад](./README.md#%EF%B8%8F-nixos-installation-flake)) і увімкніть:

    services.magshift.enable = true;

### Ubuntu / Fedora / Arch

    wget https://github.com/OleksandrCEO/MagShift/archive/refs/heads/master.zip
    unzip master.zip
    cd MagShift-master
    sudo ./install.sh

Інсталятор ставить `python3-evdev` (лише якщо його немає, команда виводиться на екран, `apt update` сам не
запускає), копіює програму в `/usr/local/bin/magshift` і додає udev-правила, тож жодних груп `input`/`uinput`
налаштовувати не треба. Наприкінці він перевіряє, чи має ваш користувач доступ до клавіатур. На X11 при першому
встановленні знадобиться перезавантаження: застосування доступу «наживо» скинуло б розкладку, задану через `setxkbmap`.

Автозапуск: у KDE через **Системні параметри → Автозапуск → Додати програму** (`magshift`), або як
[systemd user service](./README.md#-autostart-linux).

### macOS

    git clone https://github.com/OleksandrCEO/MagShift.git
    cd MagShift
    ./install-macos.sh

Без `sudo`: усе ставиться в домашню теку, автозапуск через LaunchAgent. Після встановлення відкрийте
**System Settings → Privacy & Security** і додайте бінарник Python, який покаже інсталятор, у два списки:
**Input Monitoring** та **Accessibility**. Потім перезапустіть агент:

    launchctl kickstart -k gui/$UID/com.magwer.magshift

## Використання

    magshift                 # за замовчуванням (Linux: емулює Meta+Space для перемикання)
    magshift -k alt          # якщо розкладка у вас перемикається через Alt+Shift
    magshift -k menu -p      # перемикання клавішею Menu, плюс виправлення по одиночному Pause
    magshift --list          # Linux: пристрої вводу, macOS: розкладки
    magshift --verbose       # показувати, що саме виправляється

| Опція | Що робить | Платформа |
|---|---|---|
| `-k STYLE` | Яку комбінацію ваша система використовує для перемикання розкладки: `meta` (Meta+Space, типово), `alt` (Alt+Shift), `ctrl` (Ctrl+Shift), `caps` (CapsLock), `menu` (клавіша Menu) | Linux |
| `-p` | Додатково виправляти по одиночному натисканню `Pause`, як у Punto Switcher. Подвійний Shift працює і далі | Linux |
| `--list` | Показати пристрої (Linux) або розкладки (macOS) і вийти | обидві |
| `-v` | Логувати кожне виправлення | обидві |

**На Linux стиль `-k` має збігатися з налаштуваннями системи**: MagShift не перемикає розкладку сам, а натискає ту
саму комбінацію, що й ви. На macOS `-k` не потрібен, розкладка перемикається напряму через системний API.

**X11:** MagShift друкує через розширення XTEST вашої X-сесії, тож запускайте його всередині сесії (автозапуск DE,
`exec` в i3, `.xinitrc`). Без доступу до дисплея він використовує віртуальну uinput-клавіатуру, а X.Org дає новим
клавіатурам системну розкладку (`localectl status`), а не ту, що задана через `setxkbmap`.

## Ліцензія

MIT. Можна вільно використовувати та змінювати.  
