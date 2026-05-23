import cnlunar
from datetime import datetime

n = datetime.now()
l = cnlunar.Lunar(n, godType='8char')
print('lunarYearCn       :', l.lunarYearCn)
print('lunarMonthCn      :', l.lunarMonthCn)
print('lunarDayCn        :', l.lunarDayCn)
print('year8Char         :', l.year8Char)
print('month8Char        :', l.month8Char)
print('day8Char          :', l.day8Char)
print('chineseYearZodiac :', l.chineseYearZodiac)
print('todaySolarTerms   :', l.todaySolarTerms)
print('nextSolarTerm     :', l.nextSolarTerm)
print('nextSolarTermDate :', l.nextSolarTermDate)
print('nextSolarTermYear :', l.nextSolarTermYear)
print('phenologyToday    :', getattr(l, 'phenologyToday', 'n/a'))
print('lunarYear         :', l.lunarYear)
print('lunarMonth        :', l.lunarMonth)
print('lunarDay          :', l.lunarDay)
print('isLeapMonth       :', getattr(l, 'isLunarLeapMonth', 'n/a'))
try:
    print('legal holidays   :', l.get_legalHolidays())
except Exception as e:
    print('legal holidays err:', e)
try:
    print('other festivals  :', l.get_otherFestivals())
except Exception as e:
    print('other err:', e)
try:
    print('beasts (五行/纳音):', l.year5Element, l.month5Element, l.day5Element)
except Exception as e:
    pass
