Makes annotated (molecular weights, protein names) Western blot figures from pre-rotated gel images.



Requires:
Python>=3.10
PySide6 (the dependency is installed with pip automatically)


\[How to use]

-Load pre-rotated tiff/tif/jpeg/png image (File -> Open Image)

-To create molecular weight annotation:

Tools(Image) -> Mark kDa Bands

Click on the band. A window dialogue will appear to enter kDa value. 
Any number of bands can be marked. 
If necessary, they can be cleared (Undo Last kDa or Clear All kDa).

-To create a figure:

Tools(Image) -> Crop Region, Add to Figure

Drag\&Drop to select desired area.
A window dialogue will appear to enter the protein name (or the crop name).

-To format the figure:

Click on one of the crops on the figure. 
You can set width (Figure -> Set Width) or increase/decrease it by 10% with "\[" and "]" keys.
You can move the crops with up/down arrows.

-Load another gel image to add it below.

The crops will be aligned and scaled.
Any number of images can be added.

-To export to pdf:

Figure -> Export to pdf.




\[Install and use]
In Anaconda prompt or cmd

\# activate

python -m pip install --upgrade pip

python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple wbtool

wbtool



\## Citation



If you use WBTool in published research, please cite:



Masha (RGFJ). \*WBTool: A GUI tool for annotating and assembling Western blot figures\* (2026).

GitHub repository: https://github.com/masha-rgfj/western-blot-tool

