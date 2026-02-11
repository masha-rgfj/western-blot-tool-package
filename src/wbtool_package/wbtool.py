# src/main.py
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene, QFileDialog,
    QInputDialog, QSplitter, QGraphicsLineItem, QGraphicsSimpleTextItem,
    QGraphicsRectItem, QGraphicsTextItem, QMessageBox
)
from PySide6.QtGui import QAction, QPixmap, QPen, QFont, QColor
from PySide6.QtCore import Qt, QRect, QSize, QPoint, QRectF

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
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Gel Image", "", "Image Files (*.png *.jpg *.jpeg *.tif *.tiff)"
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
        label.setFont(QFont("", 10))
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
        y0 = self.figure_next_y

        # default width = last band's width (if any)
        target_w = int(self.last_band_width) if self.last_band_width else pixmap.width()
        scaled_pm = pixmap.scaledToWidth(target_w, Qt.SmoothTransformation)
        scale = target_w / pixmap.width()   # uniform scale (height scales by same factor)
        
        pix_item = self.figure_scene.addPixmap(scaled_pm)
        #set the figure: vertically aligned to previous (if any)
        pix_item.setPos(self.figure_left_margin, y0)
        pix_item.setFlag(pix_item.GraphicsItemFlag.ItemIsSelectable, True)

        #marker Y's relative to crop top; scale them vertically by the same factor
        y_locals = [m["y"] - src_scene_rect.top() for m in markers]
        
        #markers ticks, font
        pen = QPen(Qt.black)
        tick_items = []
        for m, y_local in zip(markers, y_locals):
            y = y0 + y_local * scale
            x1 = self.figure_left_margin - 2.0
            x0 = x1 - 20.0
            line = self.figure_scene.addLine(x0, y, x1, y, pen)
            lab = QGraphicsSimpleTextItem(f"{m['kda']:g}")
            lab.setFont(QFont("", 10))
            lab.setBrush(Qt.black)
            br = lab.boundingRect()
            lab.setPos(x0 - 6.0 - br.width(), y - br.height()/2.0)
            self.figure_scene.addItem(lab)
            tick_items.append((line, lab))

        #protein name at right, vertically centered
        name_item = QGraphicsSimpleTextItem(protein_name)
        name_item.setFont(QFont("", 12))
        name_item.setBrush(Qt.black)
        nbr = name_item.boundingRect()
        name_item.setPos(self.figure_left_margin + scaled_pm.width() + 10,
                         y0 + scaled_pm.height()/2.0 - nbr.height()/2.0)
        self.figure_scene.addItem(name_item)

        #save the parameters. Add them to what the figure holds
        band = {
            "pix_item": pix_item,
            "orig_pixmap": pixmap,
            "y0": y0,
            "y_locals": y_locals,
            "ticks": tick_items,
            "name_item": name_item,
            "width": target_w
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
            if b["pix_item"].isSelected():
                self.selected_band = b
                break

    def bump_selected_width(self, factor: float):
        #changes width (called in dec/inc action when [/] pressed)
        if not self.selected_band:
            return
        new_w = max(10, int(self.selected_band["width"] * factor))
        #call the resizing function with the required parameters
        self.resize_band_by_width(self.selected_band, new_w)

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
        """Resize the selected band by width; recompute tick Y's and relayout its name."""
        scaled_pm = band["orig_pixmap"].scaledToWidth(new_width, Qt.SmoothTransformation)
        band["pix_item"].setPixmap(scaled_pm)

        scale = new_width / band["orig_pixmap"].width()
        x1 = self.figure_left_margin - 2.0
        x0 = x1 - 20.0
        for (line, lab), y_local in zip(band["ticks"], band["y_locals"]):
            y = band["y0"] + y_local * scale
            line.setLine(x0, y, x1, y)
            br = lab.boundingRect()
            lab.setPos(x0 - 6.0 - br.width(), y - br.height()/2.0)

        nbr = band["name_item"].boundingRect()
        band["name_item"].setPos(self.figure_left_margin + scaled_pm.width() + 10,
                                 band["y0"] + scaled_pm.height()/2.0 - nbr.height()/2.0)

        band["width"] = new_width
        self.last_band_width = new_width

        required_w = self.figure_left_margin + scaled_pm.width() + 10 + nbr.width() + 40
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


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1200, 750)
    win.show()
    sys.exit(app.exec())
