"""Read-only message canvas with a sparse, theme-aware paw background."""
import tkinter as tk
import customtkinter as ctk


class ConversationView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=("#FFFCFB", "#201C27"), **kwargs)
        self.messages=[]
        self.canvas=tk.Canvas(self,highlightthickness=0,borderwidth=0)
        self.scrollbar=ctk.CTkScrollbar(self,command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right",fill="y",padx=(0,3),pady=5)
        self.canvas.pack(side="left",fill="both",expand=True,padx=(5,0),pady=5)
        self.canvas.bind("<Configure>",lambda event:self.draw())
        self.canvas.bind("<MouseWheel>",self.scroll)
        self.draw()

    def scroll(self,event):
        self.canvas.yview_scroll(-int(event.delta/120),"units")
        return "break"

    def set_messages(self,messages):
        self.messages=list(messages)
        self.draw()
        self.canvas.yview_moveto(1)

    def _set_appearance_mode(self,mode):
        super()._set_appearance_mode(mode)
        if hasattr(self,"canvas"):
            self.draw()

    def draw(self):
        c=self.canvas
        bottom=c.yview()[1]>=.98
        light=ctk.get_appearance_mode()=="Light"
        c.configure(background="#FFFCFB" if light else "#201C27")
        c.delete("all")
        width=max(c.winfo_width(),100)
        y=24
        for m in self.messages:
            outgoing=m["role"]=="assistant"
            label="You" if outgoing else "Contact"
            text=c.create_text(30,y,anchor="nw",width=max(width-76,50),
                text=label+": "+m["text"],font=("Segoe UI",12),
                fill="#382630" if light else "#F8EDF8",tags="message")
            box=c.bbox(text)
            rect=c.create_rectangle(box[0]-12,box[1]-10,box[2]+12,box[3]+10,
                fill=("#FBE8EE" if outgoing else "#F3ECEF") if light else ("#3B2C48" if outgoing else "#302A39"),
                outline="",tags="message")
            c.tag_raise(text,rect)
            y=box[3]+44
        height=max(c.winfo_height(),y)
        if light:
            # Small silhouettes, staggered with generous spacing behind the messages.
            for row,py in enumerate(range(46,height,145)):
                for px in range(45+(row%2)*65,width-15,150):
                    self.paw(px,py)
            c.tag_lower("paw")
        c.configure(scrollregion=(0,0,width,height))
        if bottom:
            c.yview_moveto(1)

    def paw(self,x,y):
        color="#F5DDE7"
        # Four toe pads and a soft triangular central pad, drawn as vector shapes.
        for dx,dy,rx,ry in ((-7,0,2.1,2.8),(-2.5,-4,2.2,3),(2.7,-4,2.2,3),(7,0,2.1,2.8)):
            self.canvas.create_oval(x+dx-rx,y+dy-ry,x+dx+rx,y+dy+ry,fill=color,outline="",tags="paw")
        self.canvas.create_polygon(x-6,y+8,x-6,y+4,x-2,y+1,x,y,x+2,y+1,x+6,y+4,x+6,y+8,x+2,y+8,x,y+7,x-2,y+8,
            smooth=True,fill=color,outline="",tags="paw")
