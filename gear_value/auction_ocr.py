"""Read only the selected auction card's price; never interpret balances as prices."""
import re
from statistics import median
from PIL import Image, ImageDraw, ImageFont, ImageOps


def gold_number(text):
    text = text.strip()
    if not re.fullmatch(r'(?:[1-9]\d{0,8}|[1-9]\d{0,2}(?:[, .\u00a0]\d{3})+)', text):
        return None
    number = int(re.sub(r'[, .\u00a0]', '', text))
    return number if 1 <= number <= 1_000_000_000 else None


def selected_price(rows, width, height):
    from gear_value.recognition import normalized
    bids = [r for r in rows if 'лучшаяставка' in normalized(r['text']) and r['x'] > width * .5 and r['y'] > height * .6]
    if len(bids) == 1:
        label = bids[0]
        values = [w for r in rows if abs(r['y']-label['y']) < label['h']
                  for w in r['words'] if w['x'] > label['x'] and gold_number(w['text']) is not None]
        if len(values) == 1:
            return 'bid', values[0]
        return None
    is_detail = any('деталиснаряженияотряда' in normalized(r['text']) for r in rows)
    has_seller = any('продавец' in normalized(r['text']) and r['y'] > height * .7 for r in rows)
    if is_detail and has_seller:
        values = [w for r in rows if r['y'] > height * .85 for w in r['words']
                  if width * .68 < w['x'] < width * .92 and gold_number(w['text']) is not None]
        if len(values) == 1:
            return 'ask', values[0]
    return None


async def read_observation(image, rows, engine, directory):
    from gear_value.recognition import read_ocr
    selected = selected_price(rows, image.width, image.height)
    if not selected:
        return None
    status, word = selected
    value = gold_number(word['text'])
    # Re-read the selected number without the currency icon or adjacent lot list.
    h = word['h']
    box = (max(0, int(word['x']-2)), max(0, int(word['y']-h*.15)),
           min(image.width, int(word['x']+word['w']+2)), min(image.height, int(word['y']+h*1.15)))
    crop = image.crop(box)
    border = [crop.getpixel((x, 0)) for x in range(crop.width)]
    if median(max(pixel) for pixel in border) < 130:
        mask = Image.new('L', crop.size)
        mask.putdata([0 if max(pixel) > 120 else 255 for pixel in crop.getdata()])
    else:
        mask = crop.convert('L').point(lambda value: 255 if value > 130 else 0)
    ink = ImageOps.invert(mask).getbbox()
    if ink: mask = mask.crop(ink)
    crop = mask.resize((max(1, round(mask.width*28/mask.height)), 28))
    sheet = Image.new('RGB', (crop.width+240, 90), 'white')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 28)
    draw.text((10, 27), 'Price', fill='black', font=font)
    sheet.paste(crop, (85, 29))
    draw.text((95+crop.width, 27), 'gold', fill='black', font=font)
    lines = await read_ocr(sheet, engine, directory, 'price-check')
    candidates = [gold_number(w['text']) for line in lines for w in line['words'] if gold_number(w['text']) is not None]
    if candidates != [value]:
        return {'status':status, 'price':None, 'warning':'Цена прочитана неуверенно — укажите её вручную.'}
    return {'status':status, 'price':value}
