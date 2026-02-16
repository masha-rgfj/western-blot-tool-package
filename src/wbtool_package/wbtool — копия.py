# src/main.py
import sys
from importlib.resources import files, as_file
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QFileDialog,
    QInputDialog, QSplitter, QGraphicsLineItem, QGraphicsSimpleTextItem,
    QGraphicsRectItem, QGraphicsItem, QGraphicsTextItem, QMessageBox,
    QGraphicsPixmapItem
)
from PySide6.QtGui import QAction, QPixmap, QPen, QFont, QColor, QPainter, QPageSize
from PySide6.QtCore import Qt, QRect, QSize, QSizeF, QPoint, QRectF, QPointF
from PySide6.QtPrintSupport import QPrinter

# ---------- View that supports mark & crop ----------
class CanvasView(QGraphicsView):
    #Initializing (no rectangle until it's made)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rubberBand = None
        self.origin = QPoint()
        self.mode = None             # None | "crop" | "mark". When not in crop mode, 'None'
        self.crop_callback = None
        self.mark_callback = None

    #What to do in response to mouse
    def mousePressEvent(self, event):
        #When clicked in crop mode, make a (0,0) size rectangle
        if event.button() == Qt.LeftButton and self.mode == "crop" and self.crop_callback:
            from PySide6.QtWidgets import QRubberBand
            self.origin = event.pos() 
            if self.rubberBand is None:
                self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)
            self.rubberBand.setGeometry(QRect(self.origin, QSize())) #QSize() is (0,0) 
            self.rubberBand.show()
        
        #Upon mouse click in kDa marking mode, save the y coordinates 
        elif event.button() == Qt.LeftButton and self.mode == "mark" and self.mark_callback:
            scene_pt = self.mapToScene(event.pos())
            self.mark_callback(scene_pt.y())
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        #Resize the rectangle when mouse is dragged in crop mode
        if self.rubberBand and self.rubberBand.isVisible():
            rect = QRect(self.origin, event.pos()).normalized()
            self.rubberBand.setGeometry(rect)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        #When crop rectangle is ready, call the crop function, then exit crop mode
        if self.rubberBand and self.rubberBand.isVisible():
            self.rubberBand.hide() #no need to show anymore
            rect = QRect(self.origin, event.pos()).normalized()
            scene_rect = self.mapToScene(rect).boundingRect().toRect()
            if self.crop_callback:
                self.crop_callback(scene_rect)
            self.mode = None
        else:
            super().mouseReleaseEvent(event)


#----------- Container for one band: image+labels
class BandGroup(QGraphicsRectItem):
    def __init__(self, locked_x: float | None = None):
        super().__init__()
        self.locked_x = locked_x
        self.setPen(Qt.NoPen)
        self.setBrush(Qt.NoBrush)
        
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        
    def itemChange(self, change, value):
    # Optional: lock x so it moves only up/down
        if change == QGraphicsItem.ItemPositionChange and self.locked_x is not None:
            pos = QPointF(value)
            return QPointF(self.locked_x, pos.y())
        return super().itemChange(change, value)


# ---------- Main Window ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Western Blot Figure Tool")

        # Setting up gel image area (left)
        self.image_left_margin = 80
        self.current_pixmap = None
        self.pixmap_item = None
        self.kda_markers = []  # [{y, kda, line, text}]

        self.image_scene = QGraphicsScene(self)
        self.image_view = CanvasView(self)
        self.image_view.setScene(self.image_scene)
        self.image_view.setAlignment(Qt.AlignCenter)
        self.image_view.setBackgroundBrush(QColor(230, 230, 230))

        #Setting up figure area (right)
        self.figure_left_margin = 80
        self.figure_scene = QGraphicsScene(self)
        self.figure_view = QGraphicsView(self.figure_scene)
        self.figure_view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.figure_view.setBackgroundBrush(QColor(247, 247, 247))

        self.figure_next_y = 20
        self.figure_min_width = 900
        self.figure_scene.setSceneRect(0, 0, self.figure_min_width, 1200)

        # bands registry + selection + default size (BY WIDTH)
        self.figure_bands = []            # list of dicts (see add_band_to_figure), empty in the beginning
        self.selected_band = None
        self.last_band_width = None       # px; new bands default to this width
        self.figure_scene.selectionChanged.connect(self.on_selection_changed)

        #Layout: image area and figure area
        splitter = QSplitter(self)
        splitter.addWidget(self.image_view)
        splitter.addWidget(self.figure_view)
        splitter.setSizes([700, 700])
        self.setCentralWidget(splitter)

        #Menu bar: File, Tools, Figure
        file_menu = self.menuBar().addMenu("File")
        open_action = QAction("Open Image…", self) #How the action appears on menu
        open_action.triggered.connect(self.open_image) #open_image happens when pressed
        file_menu.addAction(open_action) #Adding the action under 'File'

        tools_menu = self.menuBar().addMenu("Tools (Image)")
        mark_action = QAction("Mark kDa Bands", self)
        mark_action.triggered.connect(self.enable_mark_mode)
        tools_menu.addAction(mark_action)

        undo_mark_action = QAction("Undo Last kDa", self)
        undo_mark_action.triggered.connect(self.undo_last_kda)
        tools_menu.addAction(undo_mark_action)

        clear_marks_action = QAction("Clear All kDa", self)
        clear_marks_action.triggered.connect(self.clear_all_kda)
        tools_menu.addAction(clear_marks_action)

        crop_action = QAction("Crop Region → Add to Figure", self)
        crop_action.triggered.connect(self.enable_crop_mode)
        tools_menu.addAction(crop_action)

        fig_menu = self.menuBar().addMenu("Figure")
        clear_fig_action = QAction("Clear Figure", self)
        clear_fig_action.triggered.connect(self.clear_figure)
        fig_menu.addAction(clear_fig_action)

        #width controls with ']' and '['
        inc_action = QAction("Increase Width (10%)", self)
        inc_action.setShortcut("]")
        inc_action.triggered.connect(lambda: self.bump_selected_width(1.10))
        fig_menu.addAction(inc_action)

        dec_action = QAction("Decrease Width (10%)", self)
        dec_action.setShortcut("[")
        dec_action.triggered.connect(lambda: self.bump_selected_width(1/1.10))
        fig_menu.addAction(dec_action)

        setw_action = QAction("Set Width…", self)
        setw_action.triggered.connect(self.set_selected_width_dialog)
        fig_menu.addAction(setw_action)
        
        #crops positioning (arrow keys)
        move_up = QAction("Move Up", self)
        move_up.setShortcut(Qt.Key_Up)          # ↑
        move_up.triggered.connect(lambda: self.nudge_selected(-5))
        self.addAction(move_up)                # important: add to window so it works anywhere
        
        move_down = QAction("Move Down", self)
        move_down.setShortcut(Qt.Key_Down)      # ↓
        move_down.triggered.connect(lambda: self.nudge_selected(5))
        self.addAction(move_down)
        
        export_pdf_action = QAction("Export Figure as PDF…", self)
        export_pdf_action.triggered.connect(self.export_figure_pdf)
        fig_menu.addAction(export_pdf_action)
        
        export_text_action = QAction("Export text", self)
        export_text_action.triggered.connect(self.export_text)
        fig_menu.addAction(export_text_action)

        self.show_startup_message()

    # ---------- Startup message ----------
    def show_startup_message(self):
        self.image_scene.clear()
        self.kda_markers.clear()
        self.pixmap_item = None
        W, H = 900, 650
        self.image_scene.setSceneRect(0, 0, W, H)
        #startup text
        html = """
        <div style="color:#444; font-family:Segoe UI, Arial, Helvetica;">
          <h2 style="margin:0">Western Blot Figure Tool</h2>
          <p style="margin:8px 0 0 0">Please <b>pre-rotate</b> your gel so bands run <b>horizontally</b>.</p>
          <ul style="margin:6px 0 0 18px">
            <li>File → <i>Open Image…</i></li>
            <li>Tools → <i>Mark kDa Bands</i> (click ladder, enter values)</li>
            <li>Tools → <i>Crop Region → Add to Figure</i></li>
          </ul>
        </div>
        """
        #message text parameters
        msg = QGraphicsTextItem()
        msg.setTextWidth(520)
        msg.setHtml(html)
        br = msg.boundingRect()
        msg.setPos((W - br.width())/2, (H - br.height())/2)
        pad = 12
        bg = QGraphicsRectItem(0, 0, br.width()+2*pad, br.height()+2*pad)
        bg.setBrush(QColor(245, 245, 245))
        bg.setPen(QPen(Qt.lightGray))
        bg.setPos(msg.x()-pad, msg.y()-pad)
        bg.setZValue(-1)
        self.image_scene.addItem(bg)
        self.image_scene.addItem(msg)

    # ---------- Image I/O ----------
    def open_image(self):
        #loads the selected image to the workplace
        data_dir = files("wbtool_package.data")
        start_dir = str(data_dir)
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Gel Image", start_dir, "Image Files (*.png *.jpg *.jpeg *.tif *.tiff)"
        )
        if not path:
            return
        pm = QPixmap(path)
        if pm.isNull():
            QMessageBox.warning(self, "Load error", "Could not load that image.")
            return
        self.current_pixmap = pm
        self.image_scene.clear()
        self.kda_markers.clear()  #Clear the previous markers info
        self.pixmap_item = self.image_scene.addPixmap(pm)
        self.pixmap_item.setPos(self.image_left_margin, 0)
        self.image_scene.setSceneRect(0, 0, pm.width()+self.image_left_margin+10, pm.height())
        self.image_view.fitInView(self.image_scene.sceneRect(), Qt.KeepAspectRatio)

    # ---------- kDa marking ----------
    def enable_mark_mode(self):
        #Switching to kDa marking mode
        if self.current_pixmap is None:
            return #Nothing happens if no image
        self.image_view.mode = "mark"
        self.image_view.mark_callback = self.add_kda_marker

    def add_kda_marker(self, scene_y: float):
        #Window dialogue asking for kDa
        val, ok = QInputDialog.getDouble(self, "kDa value", "Enter kDa:", 0.0, 0.0, 1_000_000.0, 1)
        if not ok or self.pixmap_item is None:
            return
        
        #Position & params for the marker: on the left of the image, on the clicked y
        x1 = self.image_left_margin - 2.0
        x0 = x1 - 20.0
        pen = QPen(Qt.black)
        line_item = QGraphicsLineItem(x0, scene_y, x1, scene_y)
        line_item.setPen(pen)
        self.image_scene.addItem(line_item)
        label = QGraphicsSimpleTextItem(f"{val:g}")
        label.setFont(QFont("Arial", 50))
        label.setBrush(Qt.black)
        br = label.boundingRect()
        label.setPos(x0 - 6.0 - br.width(), scene_y - br.height()/2.0)
        self.image_scene.addItem(label)
        self.kda_markers.append({"y": float(scene_y), "kda": float(val), "line": line_item, "text": label})
        self.kda_markers.sort(key=lambda d: d["y"])

    #Clear last marker
    def undo_last_kda(self):
        if not self.kda_markers:
            return
        last = self.kda_markers.pop()
        self.image_scene.removeItem(last["line"])
        self.image_scene.removeItem(last["text"])

    #Clear all markers
    def clear_all_kda(self):
        for d in self.kda_markers:
            self.image_scene.removeItem(d["line"])
            self.image_scene.removeItem(d["text"])
        self.kda_markers.clear()

    # ---------- Cropping ----------
    def enable_crop_mode(self):
        #Switcher to crop mode
        if self.current_pixmap is None:
            return
        self.image_view.mode = "crop"
        self.image_view.crop_callback = self.crop_region #None when initialized, function when switched

    def crop_region(self, scene_rect):
        #makes the cropped area with relevant MW ticks and protein name and calls a function to put it to the figure
        #change the rectangle coordinate system
        offset = self.pixmap_item.pos().toPoint()
        pix_rect = scene_rect.translated(-offset)
        cropped = self.current_pixmap.copy(pix_rect)
        if cropped.isNull():
            return
        #only markers inside the cropped area are relevant
        inside = [m for m in self.kda_markers if scene_rect.top() <= m["y"] <= scene_rect.bottom()]
        #ask the protein name
        protein, ok = QInputDialog.getText(self, "Protein name", "Enter protein name:")
        if not ok:
            return
        #call the function that adds it to the figure
        self.add_band_to_figure(cropped, inside, scene_rect, protein.strip() or "Protein")

    # ---------- Figure placement & width-based resizing ----------
    def add_band_to_figure(self, pixmap: QPixmap, markers, src_scene_rect: QRectF, protein_name: str):
        #adds the cropped area with ticks and annotation to the figure
        #code-wise: creates the bandgroup; all items are children -> move together
        

        # default width = last band's width (if any)
        target_w = int(self.last_band_width) if self.last_band_width else pixmap.width()
        scaled_pm = pixmap.scaledToWidth(target_w, Qt.SmoothTransformation)
        scale = target_w / pixmap.width()   # uniform scale (height scales by same factor)
        
        
        #making movable selectable container
        y0 = self.figure_next_y
        group = BandGroup(locked_x=self.figure_left_margin)   # lock_x=None for free movement
        group.setRect(0, 0, scaled_pm.width(), scaled_pm.height())  # hitbox size
        group.setPos(self.figure_left_margin, y0)
        group.setHandlesChildEvents(True)  # clicking/dragging children drags the group
        self.figure_scene.addItem(group)
        
        #image as a child of the group
        pix_item = QGraphicsPixmapItem(scaled_pm, group)
        pix_item.setPos(0, 0)
        
        # black frame around the crop (image area)
        border = QGraphicsRectItem(0, 0, scaled_pm.width(), scaled_pm.height(), group)
        border.setPen(QPen(Qt.black, 1.5))
        border.setBrush(Qt.NoBrush)
        border.setZValue(10)  # above image
        border.setAcceptedMouseButtons(Qt.NoButton)
        # Important: let mouse events go to the group (so dragging works from the image)
        pix_item.setAcceptedMouseButtons(Qt.NoButton)    
        

        #marker Y's relative to crop top; scale them vertically by the same factor
        y_locals = [m["y"] - src_scene_rect.top() for m in markers]
        
        #Add ticks + labels as children of the group (negative x = outside the image)
        pen = QPen(Qt.black)
        tick_items = []
        x1 = -2.0
        x0 = x1 - 20.0  # 20 px tick length
        
        for m, y_local in zip(markers, y_locals):
            y = y_local * scale
            
            line = QGraphicsLineItem(x0, y, x1, y, group)
            line.setPen(pen)
            line.setAcceptedMouseButtons(Qt.NoButton)
            
            lab = QGraphicsSimpleTextItem(f"{m['kda']:g}", group)
            lab.setFont(QFont("Arial", 10))
            lab.setBrush(Qt.black)
            br = lab.boundingRect()
            lab.setPos(x0 - 6.0 - br.width(), y - br.height() / 2.0)
            lab.setAcceptedMouseButtons(Qt.NoButton)

            tick_items.append((line, lab))

        #protein name at right, vertically centered; child of the group
        name_item = QGraphicsSimpleTextItem(protein_name, group)
        name_item.setFont(QFont("Arial", 12))
        name_item.setBrush(Qt.black)
        nbr = name_item.boundingRect()
        name_item.setPos(scaled_pm.width() + 10, scaled_pm.height() / 2.0 - nbr.height() / 2.0)
        name_item.setAcceptedMouseButtons(Qt.NoButton)

        #save the parameters. Add them to what the figure holds
        band = {
            "group": group,
            "pix_item": pix_item,
            "orig_pixmap": pixmap,
            "y_locals": y_locals,
            "ticks": tick_items,
            "name_item": name_item,
            "width": target_w,
            "border_item": border
        }
        self.figure_bands.append(band)
        self.selected_band = band
        self.last_band_width = target_w


        required_w = self.figure_left_margin + scaled_pm.width() + 10 + nbr.width() + 40
        #if too big, scale
        if required_w > self.figure_scene.sceneRect().width():
            r = self.figure_scene.sceneRect()
            self.figure_scene.setSceneRect(0, 0, max(required_w, self.figure_min_width), r.height())

        self.figure_next_y += scaled_pm.height() + 30
        if self.figure_next_y + 200 > self.figure_scene.sceneRect().height():
            r = self.figure_scene.sceneRect()
            self.figure_scene.setSceneRect(0, 0, r.width(), r.height() + 800)
        
        #autocsrolls so that it's visible
        self.figure_view.ensureVisible(0, self.figure_next_y, 10, 10)

    def on_selection_changed(self):
        #changes the selected crop ('band') when clicked (called when clicked)
        self.selected_band = None
        for b in self.figure_bands:
            if b["group"].isSelected():
                self.selected_band = b
                break

    def bump_selected_width(self, factor: float):
        #changes width (called in dec/inc action when [/] pressed)
        if not self.selected_band:
            return
        new_w = max(10, int(self.selected_band["width"] * factor))
        #call the resizing function with the required parameters
        self.resize_band_by_width(self.selected_band, new_w)
    
    def nudge_selected(self, dy: int):
        if not self.selected_band:
            return
        g = self.selected_band["group"]
        # keep x locked to the left margin; only change y
        g.setPos(self.figure_left_margin, g.pos().y() + dy)


    def set_selected_width_dialog(self):
        #changes width if specified
        if not self.selected_band:
            return
        cur = int(self.selected_band["width"])
        val, ok = QInputDialog.getInt(self, "Set width", "Width (pixels):", cur, 10, 20000, 1)
        if ok:
            #call the resizing function with the required parameters
            self.resize_band_by_width(self.selected_band, int(val))

    def resize_band_by_width(self, band: dict, new_width: int):
        """Resize a band (BandGroup version): scale image by width and reposition ticks/name inside the group."""
        scaled_pm = band["orig_pixmap"].scaledToWidth(new_width, Qt.SmoothTransformation)
        band["pix_item"].setPixmap(scaled_pm)
    
        # Update the group's hitbox to match new image size
        band["group"].setRect(0, 0, scaled_pm.width(), scaled_pm.height())
        band["border_item"].setRect(0, 0, scaled_pm.width(), scaled_pm.height())
        scale = new_width / band["orig_pixmap"].width()
    
        # Tick x positions are relative to group (negative = outside the image)
        x1 = -2.0
        x0 = x1 - 20.0
    
        for (line, lab), y_local in zip(band["ticks"], band["y_locals"]):
            y = y_local * scale
            line.setLine(x0, y, x1, y)
    
            br = lab.boundingRect()
            lab.setPos(x0 - 6.0 - br.width(), y - br.height() / 2.0)
    
        # Protein name stays to the right of the image, centered vertically
        nbr = band["name_item"].boundingRect()
        band["name_item"].setPos(
            scaled_pm.width() + 10,
            scaled_pm.height() / 2.0 - nbr.height() / 2.0
        )
    
        band["width"] = new_width
        self.last_band_width = new_width
    
        # Grow the figure scene width if needed (use the group's scene position)
        group_x = band["group"].scenePos().x()
        required_w = group_x + scaled_pm.width() + 10 + nbr.width() + 40
        if required_w > self.figure_scene.sceneRect().width():
            r = self.figure_scene.sceneRect()
            self.figure_scene.setSceneRect(0, 0, max(required_w, self.figure_min_width), r.height())


    def clear_figure(self):
        self.figure_scene.clear()
        self.figure_bands.clear()
        self.selected_band = None
        self.figure_next_y = 20
        self.last_band_width = None
        self.figure_scene.setSceneRect(0, 0, self.figure_min_width, 1200)
    
    def export_text(self): #test function
        path, _ = QFileDialog.getSaveFileName(self, "Write text", "file.txt", "TXT (*.txt)")
        if not path:
            return
        text, ok = QInputDialog.getText(self, "text", "Enter text:")
        if not ok:
            return
        with open(path, 'w') as f:
            f.write(text)
        
    
    def export_figure_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", "figure.pdf", "PDF (*.pdf)")
        if not path:
            return
        
        # Tight bounding box of what's in the scene
        content = self.figure_scene.itemsBoundingRect()
        if content.isNull():
            QMessageBox.information(self, "Nothing to export", "Figure is empty.")
            return
        # Choose a DPI (300 is typical for papers; 600 for very fine gels)
        dpi, ok = QInputDialog.getInt(self, "PDF DPI", "Raster DPI for images:", 300, 72, 1200, 1)
        if not ok:
            return
    
        # QPrinter in PDF mode
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(path)
        printer.setResolution(dpi)
    
        # Standard a4
        printer.setPageSize(QPageSize.A4)
    
        painter = QPainter(printer)
    #     painter.setRenderHint(QPainter.Antialiasing, True)
    #     painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        
        page = QRectF(printer.pageRect(QPrinter.DevicePixel))
    
        # Fit scene content into the printable page while preserving aspect ratio
        sx = page.width() / content.width()
        sy = page.height() / content.height()
        s = min(sx, sy)  # uniform scale to fit
        
        # Center it on the page
        target_w = content.width() * s
        target_h = content.height() * s
        target = QRectF(
            page.left() + (page.width() - target_w) / 2.0,
            page.top()  + (page.height() - target_h) / 2.0,
            target_w,
            target_h
            )

        self.figure_scene.render(painter, target=target, source=content)
        painter.end()

    
    #     painter.end()

# if __name__ == "__main__":
#     app = QApplication.instance()
#     if app is None:
#         app = QApplication(sys.argv) 
#     win = MainWindow()
#     #win.resize(1200, 750)
#     win.show()
#     sys.exit(app.exec())


#making callable as 'wbtool'
def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    win = MainWindow()
    win.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())