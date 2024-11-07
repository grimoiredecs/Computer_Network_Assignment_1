import sys
import os
import bencode_
import re #regex
'''
 open(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None)
'''

'''
PDF imaging model

Objects that are placed on PDF pages are called ‘marks’. The page surface is called the ‘canvas’.

    A coordinate system is used to define where each mark is placed. By default, coordinates are defined in points (72 units per inch) but this measurement system can be redefined within a PDF. The origin is in the bottom left but this 0,0 coordinate can also be redefined. This flexible coordinate system is called ‘User Space’. Afterward when a PDF is sent to an output device such as a printer, the RIP needs to recalculate everything to ‘Device Space’, the coordinate system of the output device.
    Marks can have a number of characteristics:
        a fill
        a stroke
        a color, which can be defined in one of the color spaces that PDF supports (11 in the most recent versions)
        a certain level of transparency (from PDF 1.4 onwards)
    All graphic objects are either
        paths – shapes made out of lines, curves and or rectangles
        text
        bitmap images
        Form XObjects – which are reusable elements
        PostScript language fragments – worst case
    Some of the content of a PDF can be optional content, marks that can be selectively viewed or hidden. In Acrobat optional content is somewhat misleadingly referred to as ‘layers’. Some practical examples of this:
        Maps that contain a coordinate grid that can be activated/deactivated
        Brochures with text in multiple languages
        Packaging files with the die-cut and embossing information as separate optional content.
(source:  https://www.prepressure.com/pdf/basics/fileformat)

'''
'''
with open('Reference_NetApp.pdf', 'rb') as file: #raw byte reading
    raw_byte = file.read()  
    print(raw_byte)

'''

byts = b'0x0009'

with open('new.txt','rb') as file:
    raw_txt = file.read()
    print(raw_txt)
print(bencode_.bdecode(open('alice.torrent','rb').read()))
