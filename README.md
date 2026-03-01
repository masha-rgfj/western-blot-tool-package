# WBtool

Makes annotated (molecular weights, protein names) composite Western blot figures from pre-rotated gel images



Requires:

Python>=3.10

PySide6 (the dependency is installed with pip automatically)


# [How to use]

https://github.com/user-attachments/assets/6898f4a9-a5b1-4ea6-963c-7ad733fdd58b


**-Load pre-rotated gel image (tiff/tif/jpeg/png):**

File -> Open Image


**-Create molecular weight annotation:**

Tools(Image) -> Mark kDa Bands

Click on the band. A window dialogue will appear to enter kDa value. 
Any number of bands can be marked. 
If necessary, they can be cleared (Undo Last kDa or Clear All kDa).


**-Add the crop to the figure:**

Tools(Image) -> Crop Region, Add to Figure

Drag\&Drop to select desired area.
A window dialogue will appear to enter the protein name (or the crop name).


**-Format the figure:**

Click on one of the crops on the figure. 
You can set width (Figure -> Set Width) or increase/decrease it by 10% with "\[" and "]" keys.
You can move the crops with up/down arrows.


**-Load another gel image to add another crop**

The crops will be aligned and scaled.
Any number of images can be added.


**-Export to pdf:**

Figure -> Export to pdf.


## [Run as a script]
**wbtool.py** in the scripts folder. Requires installed PySide6. 
Several versions are available:

**wbtool_samplenames.py** - allows adding lanes annotation above the gel 

**wbtool_vertical.py** - optimized for vertical stripes (stacks gel crops horizontally)




## [Install as a package]

In Anaconda prompt or cmd

\# activate
```
python -m pip install --upgrade pip

python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple wbtool

wbtool
```



## Citation


If you use WBTool in published research, please cite:



Masha (RGFJ). \*WBTool: A GUI tool for annotating and assembling Western blot figures\* (2026).

GitHub repository: https://github.com/masha-rgfj/western-blot-tool-package





