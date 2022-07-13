#!/usr/bin/env python
"""PSU_Control.py: Controls a RS232 SERIAL INTERFACE from Delta Elektonika, providing a gui."""

__author__      = "Owen Dennis McGinnis"
__version__     = "1.0"
# Version A: Frontpanel locking disabled
__email__       = "mcginnis@atom.uni-frankfurt.de"


import pathlib
import tkinter as tk
import tkinter.ttk as ttk
import pygubu
import serial.tools.list_ports
import serial
import os
import re
# Open a file in default viewer
# os.startfile(PROJECT_PATH / "bachelor_McGinnis.pdf")
# Remember to add file to exe compilation
from pygubu.builder import tkstdwidgets, ttkstdwidgets
from time import sleep

PROJECT_PATH = pathlib.Path(__file__).parent
PROJECT_UI = PROJECT_PATH / "PSU_Control.ui"
ICON_PATH  = PROJECT_PATH / "Icon.png"
DOCUMENTAION_PATH  = PROJECT_PATH / "PSU_Control_manual.pdf"
DEVICE_COM_NAME = "USB Serial Port"  # Name for testing arduino
DEVICE_COM_REGEX = "{} [(].*[)]".format(DEVICE_COM_NAME)


class printableError(Exception):
    pass

class PsuControlCom:
    def __init__(self, channel=1):
        self.status     = -1
        self.isRemote   = -1
        self.frontpanel = -1
        self.voltageSet = None
        self.currentSet = None
        self.voltageMeasured = None
        self.currentMeasured = None
        self.voltageMax = 0
        self.currentMax = 0
        self.voltageRequested = None
        self.currentRequested = None
        self.serialConnection = None
        self.channel = channel
        self.readErrorCount = 0
    
    def __del__(self):
        if self.serialConnection is not None:
            self.serialConnection.close()
    
    def write(self, command):
        print("Sending:", command)
        self.checkConnection(1)
        try:
            self.serialConnection.write("{}\n".format(command).encode("utf-8"))
        except serial.serialutil.SerialException as err:
            self.serialConnection.close()
            self.serialConnection = None
            raise printableError("{}\nClosing connection".format(err))
        return self
    
    def read(self, delay=None):
        self.checkConnection(0)
        if delay is not None:
            sleep(delay)
            self.checkConnection(0)
        try:
            # TODO Fix expected to \n\r\x04
            # ValueError: invalid literal for int() with base 10: '1\n\r\x04'
            data = self.serialConnection.read_until(expected="\x04").decode("utf-8")
            print(repr(data))
            data = data.replace("\n","").replace("\r","").replace("\04","")
            #data = data[:-3]
        except serial.serialutil.SerialException as err:
            self.serialConnection.close()
            self.serialConnection = None
            raise printableError("{}\nClosing connection".format(err))
        print("Received:", data)
        if data is None or data == "":
            self.readErrorCount += 1
            if self.readErrorCount >= 3:
                self.serialConnection.close()
                self.serialConnection = None
                raise printableError("Could not read from serial interface too often!\nClosing Connection")
            else:
                raise printableError("Could not read from serial interface")
        self.readErrorCount = 0
        return data
    
    def close(self):
        self.serialConnection.close()
        self.serialConnection = None
    
    def open(self, port, baudrate=9600):
        if self.serialConnection is not None:
            self.serialConnection.close()
            self.serialConnection = None
        
        try:
            self.serialConnection = serial.Serial(port=port, baudrate=baudrate, timeout=0.2, writeTimeout=5)
            if not self.serialConnection.is_open:
                self.serialConnection.open()
        except serial.SerialException:
            self.serialConnection.close()
            raise printableError("The serial connection could not be established, because either\nthe device was not found or could not be configured.")
        else:
            self.readErrorCount = 0
            return self
    
    def is_connected(self, val=-1):
        if self.serialConnection is not None:
            if self.serialConnection.is_open:
                return True
        return False
    
    def checkConnection(self, val=-1):
        if self.serialConnection is None:
            raise printableError("Connection is not jet established!\nPlease select a port.")
        else:
            if not self.serialConnection.is_open:
                raise printableError("Connection is not jet established!\nPlease select a port.")
            if not self.is_connected(val):
                raise printableError("Connection is not avialable or is faulty!\nPlease check connection.")
    
    def initialCom(self):
        for _ in range(5):
            try:
                self.setChannel(self.channel).updateStatus()
            except printableError as err:
                if str(err) != "Could not read from serial interface":
                    raise printableError(err)
                sleep(1)
                continue
            else:
                break
        self.updateRemoteStatus() \
            .updateMaxValues() \
            .updateSetCurrent() \
            .updateSetVoltage() \
            .updateFrontpanelStatus()\
            .updateMeasuredCurrent() \
            .updateMeasuredVoltage()
        return self
    
    def saveUpdate(self):
        self.setChannel(self.channel)
        self.updateStatus() \
            .updateRemoteStatus() \
            .updateMaxValues() \
            .updateSetCurrent() \
            .updateSetVoltage()
        return self
    
    def fullUpdate(self):
        self.saveUpdate() \
            .updateMeasuredCurrent() \
            .updateMeasuredVoltage()
        return self
    
    def setChannel(self, channel):
        if not 0 < channel < 30:
            raise Exception("Communication channel is not within range! (0<channel<30)")
        self.write("CH {}".format(channel))
        self.readChannel()
        return self
    
    def readChannel(self):
        self.channel = int(self.write("CH?").read())
        return self
    
    def updateStatus(self):
        rsd = int(self.write("SOurce:FUnction:RSD?").read())
        power = int(self.write("SOurce:FUnction:OUTP?").read())
        self.status = 0 if (rsd == 0 and power==1) else 1
        return self
    
    def updateRemoteStatus(self):
        remCV = int(self.write("REMote:CV?").read())
        remCC = int(self.write("REMote:CC?").read())
        self.isRemote = remCV * remCC
        return self
    
    def updateMaxValues(self):
        self.voltageMax = float(self.write("SOur:VOlt:MAx?").read())
        self.currentMax = float(self.write("SOur:CUrr:MAx?").read())
        return self
    
    def updateSetCurrent(self):
        self.currentSet = float(self.write("SOurce:CUrrent?").read())
        return self
    
    def updateSetVoltage(self):
        self.voltageSet = float(self.write("SOurce:VOltage?").read())
        return self
    
    def updateMeasuredCurrent(self):
        if self.status == 0:
            self.currentMeasured = float(self.write("MEasure:CUrrent?").read(2))
        else:
            self.currentMeasured = -1
        return self
    
    def updateMeasuredVoltage(self):
        if self.status == 0:
            self.voltageMeasured = float(self.write("MEasure:VOltage?").read(2))
        else:
            self.voltageMeasured = -1
        return self
    
    def setVoltage(self):
        self.write("SOurce:VOltage {}".format(self.voltageRequested))
        return self
    
    def setCurrent(self):
        self.write("SOurce:CUrrent {}".format(self.currentRequested))
        return self
    
    def voltageRequestedSet(self, val):
        if self.voltageMax < val:
            raise printableError("Voltage is not in range.\nMax Voltage is {} V".format(self.voltageMax))
        elif val < 0:
            raise printableError("Voltage is not in range.\nMin Voltage is 0 V".format(self.voltageMax))
        self.voltageRequested = val
        return self
    
    def currentRequestedSet(self, val):
        if self.currentMax < val:
            raise printableError("Current is not in range.\nMax Current is {} A".format(self.voltageMax))
        elif val < 0:
            raise printableError("Current is not in range.\nMin Current is 0 A".format(self.voltageMax))
        self.currentRequested = val
        return self
    
    def psuOn(self):
        self.write("SOurce:FUnction:RSD 0")
        self.write("SOurce:FUnction:OUTP ON")
        self.updateStatus()
        return self
    
    def psuOff(self):
        self.write("SOurce:FUnction:RSD 1")
        self.write("SOurce:FUnction:OUTP OFF")
        self.updateStatus()
        return self
    
    def psuRemote(self):
        self.write("REMote:CC").write("REMote:CV").updateRemoteStatus()
        self.write("SOurce:FUnction:OUTP ON")
        self.updateStatus()
        return self
    
    def psuLocal(self):
        self.write("LOCal:CC").write("LOCal:CV").updateRemoteStatus()
        self.write("SOurce:FUnction:OUTP ON")
        self.updateStatus()
        return self
    
    def updateFrontpanelStatus(self):
        #self.frontpanel = int(self.write("SOurce:FUnction:FRontpanel:Lock?").read())
        return self
    
    def fpLock(self):
        #self.write("SOurce:FUnction:FRontpanel:Lock Lock").updateFrontpanelStatus()
        return self
    
    def fpUnlock(self):
        #self.write("SOurce:FUnction:FRontpanel:Lock Unlock").updateFrontpanelStatus()
        return self

class PsuControlApp:
    def __init__(self, master=None):
        self.builder = builder = pygubu.Builder()
        builder.add_resource_path(PROJECT_PATH)
        builder.add_from_file(PROJECT_UI)
        self.mainwindow = builder.get_object('mainwindow', master)
        self.img_Icon = tk.PhotoImage(file=ICON_PATH)
        self.mainwindow.iconphoto(True, self.img_Icon)
        
        self.userSetVoltage = None
        self.userSetCurrent = None
        self.errorMsg = None
        self.selectedChannel = 0
        self.selectedChannelTxt = None
        builder.import_variables(
            self, ["userSetVoltage", "userSetCurrent", "errorMsg", "selectedChannel", "selectedChannelTxt",]
        )
        
        builder.connect_callbacks(self)
        
        self.dialogLocal  = None
        self.initDialogLocal(self.mainwindow)
        self.dialogRemote = None
        self.initDialogRemote(self.mainwindow)
        
        self.selectedPort = 1
        self.coms= [PsuControlCom(i) for i in range(1,16)]
        self.com = self.coms[0]
    
    def initDialogLocal(self, master):
        # build ui
        self.dialogLocal = tk.Tk() if master is None else tk.Toplevel(master)
        self.message9 = tk.Message(self.dialogLocal)
        self.message9.configure(font='TkDefaultFont', text='Are you shure you want to switch to the local settings?\n\nWARNING: The power supply will return to the potentiometers settings on the front panel!', width='350')
        self.message9.grid(column='0', columnspan='2', padx='10', pady='10', row='0')
        self.dialogLocal.columnconfigure('0', pad='20')
        self.buttonLocalConfirm = ttk.Button(self.dialogLocal)
        self.buttonLocalConfirm.configure(takefocus=True, text='Confirm')
        self.buttonLocalConfirm.grid(column='0', row='1')
        self.dialogLocal.rowconfigure('1', pad='30')
        self.buttonLocalConfirm.configure(command=self.psuLocal)
        self.button12 = ttk.Button(self.dialogLocal)
        self.button12.configure(takefocus=True, text='Abort')
        self.button12.grid(column='1', row='1')
        self.dialogLocal.columnconfigure('1', pad='20')
        self.button12.configure(command=self.psuLocalDialogClose)
        self.dialogLocal.configure(height='200', width='200')
        self.dialogLocal.title('Switch to Local?')
        self.dialogLocal.withdraw()
    
    def initDialogRemote(self, master):
        # build ui
        self.dialogRemote = tk.Tk() if master is None else tk.Toplevel(master)
        self.message10 = tk.Message(self.dialogRemote)
        self.message10.configure(font='TkDefaultFont', justify='left', text='Are you shure you want to switch to the remote settings?\n\nWARNING: The power supply will return to the set Voltage and Current!', width='350')
        self.message10.grid(column='0', columnspan='2', ipadx='10', ipady='10', row='0')
        self.dialogRemote.columnconfigure('0', pad='20')
        self.button13 = ttk.Button(self.dialogRemote)
        self.button13.configure(takefocus=True, text='Confirm')
        self.button13.grid(column='0', row='1')
        self.dialogRemote.rowconfigure('1', pad='30')
        self.button13.configure(command=self.psuRemote)
        self.button14 = ttk.Button(self.dialogRemote)
        self.button14.configure(takefocus=True, text='Abort')
        self.button14.grid(column='1', row='1')
        self.dialogRemote.columnconfigure('1', pad='20')
        self.button14.configure(command=self.psuRemoteDialogClose)
        self.dialogRemote.configure(height='200', width='200')
        self.dialogRemote.title('Switch to Remote?')
        self.dialogRemote.withdraw()
    
    def run(self):
        self.updateListings(True)
        self.mainwindow.mainloop()
    
    def updatePorts(self):
        pList  = self.builder.get_object("portList")
        ports = serial.tools.list_ports.comports()
        pList["values"] = [port for port in ports]
        
        print("\nPrinting all available ports:")
        for port in ports:
            print(port.name, "-", port.description)
        print()
        return self
    
    def preselectPort(self):
        if DEVICE_COM_NAME == "" or DEVICE_COM_NAME is None:
            return self
        pList  = self.builder.get_object("portList")
        ports = serial.tools.list_ports.comports()
        for port in ports:
            print(port.name, "-", port.description)
            if bool(re.match(DEVICE_COM_REGEX, port.description)):
                pList.set(port)
        return self
    
    def getSelectedPort(self):
        pList  = self.builder.get_object("portList")
        selected = pList.get()
        ports = serial.tools.list_ports.comports()
        self.selectedPort = None
        for port in ports:
            if selected == str(port):
                if self.selectedPort is None:
                    self.selectedPort = port
                else:
                    raise ValueError("Port Duplicate found - should not happen")
        
        for com in self.coms:
            if com.serialConnection is not None:
                com.close()
        
        
        if self.selectedPort is not None:
            try:
                self.errorMsg.set("")
                self.connectionStatus("   Working   ")
                self.mainwindow.update()
                self.com.open(self.selectedPort.name)
                self.com.initialCom()
                self.updateListings()
                self.mainwindow.after(120000, self.updateCom, True)
            except printableError as err:
                self.errorMsg.set(err)
            else:
                self.errorMsg.set("")
        return self
    
    def lock(self, oID):
        lockButton = self.builder.get_object(oID)
        portList   = self.builder.get_object("portList")
        updateButton=self.builder.get_object("selectPortButton")
        
        if lockButton["text"] == "Unlock":
            updateButton["state"] = "normal"
            portList["state"]     = "readonly"
            lockButton["text"]    = "Lock"
        else:
            updateButton["state"] = "disabled"
            portList["state"]     = "disabled"
            lockButton["text"]    = "Unlock"

    def setUserVoltage(self):
        try:
            self.com.voltageRequestedSet(self.userSetVoltage.get())
            self.updateListings()
            self.com.setVoltage() \
                    .updateSetVoltage()
            self.updateListings()
        except tk.TclError:
            self.errorMsg.set("Input for Voltage must be a floating point number or integer!")
        except printableError as err:
            self.errorMsg.set(err)
        else:
            self.errorMsg.set("")

    def setUserCurrent(self):
        try:
            self.com.currentRequestedSet(self.userSetCurrent.get())
            self.updateListings()
            self.com.setCurrent() \
                    .updateSetCurrent()
            self.updateListings()
        except tk.TclError:
            self.errorMsg.set("Input for Current must be a floating point number or integer!")
        except printableError as err:
            self.errorMsg.set(err)
        else:
            self.errorMsg.set("")
    
    def remeasure(self):
        try:
            self.connectionStatus("   Working   ")
            self.mainwindow.update()
            self.com.fullUpdate()
        except printableError as err:
            self.errorMsg.set(err)
        else:
            self.errorMsg.set("")
    
    def updateStatusPowerDisplay(self, status=-1):
        onIndicator = self.builder.get_object("buttonPSUOn")
        offIndicator= self.builder.get_object("buttonPSUOff")
        if   status == 0:
            # PSU is in Remote
            onIndicator["background"] = "#00ff00"
            offIndicator["background"]= "#770000"
            onIndicator["activebackground"] = "#00ff00"
            offIndicator["activebackground"]= "#770000"
            onIndicator["state"] = "disabled"
            offIndicator["state"] = "active"
        elif status == 1:
            # PSU is in Local
            onIndicator["background"] = "#00aa00"
            offIndicator["background"]= "#ff0000"
            onIndicator["activebackground"] = "#00aa00"
            offIndicator["activebackground"]= "#ff0000"
            onIndicator["state"] = "active"
            offIndicator["state"] = "disabled"
        else:
            # Status is unknown
            onIndicator["background"] = "#00aa00"
            offIndicator["background"]= "#770000"
            onIndicator["activebackground"] = "#00aa00"
            offIndicator["activebackground"]= "#770000"
            onIndicator["state"] = "disabled"
            offIndicator["state"] = "disabled"
    
    def psuOn(self):
        print("Turn PSU On")
        try:
            self.com.psuOn()
        except printableError as err:
            self.errorMsg.set(err)
        else:
            self.errorMsg.set("")

    def psuOff(self):
        print("Turn PSU Off")
        try:
            self.com.psuOff()
        except printableError as err:
            self.errorMsg.set(err)
        else:
            self.errorMsg.set("")
    
    def updateStatusRemoteDisplay(self, status=-1):
        onIndicator = self.builder.get_object("buttonRemote")
        offIndicator= self.builder.get_object("buttonLocal")
        if   status == 0:
            # PSU is On
            onIndicator["background"] = "#00aa00"
            offIndicator["background"]= "#ffff00"
            onIndicator["activebackground"] = "#00aa00"
            offIndicator["activebackground"]= "#ffff00"
            onIndicator["state"] = "active"
            offIndicator["state"] = "disabled"
        elif status == 1:
            # PSU is Off
            onIndicator["background"] = "#00ff00"
            offIndicator["background"]= "#aaaa00"
            onIndicator["activebackground"] = "#00ff00"
            offIndicator["activebackground"]= "#aaaa00"
            onIndicator["state"] = "disabled"
            offIndicator["state"] = "active"
        else:
            # Status is unknown
            onIndicator["background"] = "#00aa00"
            offIndicator["background"]= "#aaaa00"
            onIndicator["activebackground"] = "#00aa00"
            offIndicator["activebackground"]= "#aaaa00"
            onIndicator["state"] = "disabled"
            offIndicator["state"] = "disabled"
    
    def psuLocalDialog(self):
        try:
            self.dialogLocal.deiconify()
        except tk.TclError:
            self.initDialogLocal(self.mainwindow)
            self.dialogLocal.deiconify()
        #self.initDialogLocal(self.mainwindow)
    
    def psuLocal(self):
        print("Switch PSU to Local")
        self.dialogLocal.withdraw()
        try:
            self.com.psuLocal()
        except printableError as err:
            self.errorMsg.set(err)
        else:
            self.errorMsg.set("")

    def psuLocalDialogClose(self):
        self.dialogLocal.withdraw()

    def psuRemoteDialog(self):
        try:
            self.dialogRemote.deiconify()
        except tk.TclError:
            self.initDialogRemote(self.mainwindow)
            self.dialogRemote.deiconify()
    
    def psuRemote(self):
        print("Switch PSU to Remote")
        self.dialogRemote.withdraw()
        try:
            self.com.psuRemote()
        except printableError as err:
            self.errorMsg.set(err)
        else:
            self.errorMsg.set("")

    def psuRemoteDialogClose(self):
        self.dialogRemote.withdraw()
    
    def updateFrontpanelLock(self, status=-1):
        onIndicator = self.builder.get_object("fpLocked")
        offIndicator= self.builder.get_object("fpUnlocked")
        if   status == 0:
            # PSU is On
            onIndicator["background"] = "#00aaaa"
            offIndicator["background"]= "#ffff00"
            onIndicator["activebackground"] = "#00aaaa"
            offIndicator["activebackground"]= "#ffff00"
            onIndicator["state"] = "active"
            offIndicator["state"] = "disabled"
        elif status == 1:
            # PSU is Off
            onIndicator["background"] = "#00ffff"
            offIndicator["background"]= "#aaaa00"
            onIndicator["activebackground"] = "#00ffff"
            offIndicator["activebackground"]= "#aaaa00"
            onIndicator["state"] = "disabled"
            offIndicator["state"] = "active"
        else:
            # Status is unknown
            onIndicator["background"] = "#00aaaa"
            offIndicator["background"]= "#aaaa00"
            onIndicator["activebackground"] = "#00aaaa"
            offIndicator["activebackground"]= "#aaaa00"
            onIndicator["state"] = "disabled"
            offIndicator["state"] = "disabled"
    
    def frontpanelLock(self):
        try:
            self.com.fpLock()
        except printableError as err:
            self.errorMsg.set(err)
        else:
            self.errorMsg.set("")
    
    def frontpanelUnlock(self):
        try:
            self.com.fpUnlock()
        except printableError as err:
            self.errorMsg.set(err)
        else:
            self.errorMsg.set("")
        
    
    def updateListings(self, loop=False):
        com = self.com
        bu = self.builder
        self.updateStatusPowerDisplay(com.status)
        self.updateStatusRemoteDisplay(com.isRemote)
        self.updateFrontpanelLock(com.frontpanel)
        self.connectionStatus()
        bu.get_object("messageVSetz")["text"] = formatNum(com.voltageRequested, "V")
        bu.get_object("messageASetz")["text"] = formatNum(com.currentRequested, "A")
        bu.get_object("messageVPSU")["text"] = formatNum(com.voltageSet, "V")
        bu.get_object("messageAPSU")["text"] = formatNum(com.currentSet, "A")
        bu.get_object("messageVMea")["text"] = formatNum(com.voltageMeasured, "V")
        bu.get_object("messageAMea")["text"] = formatNum(com.currentMeasured, "A")
        self.mainwindow.update()
        if loop:
            self.mainwindow.after(1000, self.updateListings, True)
    
    def updateCom(self, loop=False):
        self.connectionStatus("   Working   ")
        self.mainwindow.update()
        try:
            if self.com.is_connected():
                self.com.saveUpdate()
                if loop:
                    self.mainwindow.after(120000, self.updateCom, True)
        except ValueError as err:
            print("ValueError:", err)
        else:
            self.updateListings()
        return self
        
    def openDocu(self):
        os.startfile(DOCUMENTAION_PATH)
    
    def connectionStatus(self, alt=None):
        msgBox = self.builder.get_object("message3")
        if alt is not None:
            msgBox["background"] = "#ffff00"
            msgBox["foreground"] = "#000000"
            msgBox["text"] = "{:<13}".format(alt)
            return self
        if self.com.is_connected():
            msgBox["background"] = "#00ff00"
            msgBox["foreground"] = "#000000"
            msgBox["text"] = "  Connected  "
        else:
            msgBox["background"] = "#ff0000"
            msgBox["foreground"] = "#ffffff"
            msgBox["text"] = "Not connected"
        return self
    
    def confirmChannel(self):
        self.connectionStatus("   Working   ")
        self.mainwindow.update()
        try:
            port = self.selectedChannel.get()
            self.com = self.coms[port-1]
            if not self.com.is_connected():
                self.getSelectedPort()
            else:
                self.updateCom()
        except printableError as err:
            self.errorMsg.set(err)
        else:
            self.selectedChannelTxt.set("Selected Channel: {}".format(port))
            self.errorMsg.set("")
        return self

def formatNum(number, unit):
    steps=[(1e6, "M", 1e-6), (1e3, "k", 1e-3), (1, " ", 1), (1e-3, "m", 1e3), (1e-6, "μ", 1e6)]
    if number is None:
        return "---.-- {}".format(unit)
    if number == 0:
        return "{: >6.2f}{}{}".format(number, " ", unit)
    for test, char, mult in steps:
        if abs(number) >= test:
            return "{: >6.2f}{}{}".format(number * mult, char, unit)
    else:
        test,char,mult = steps[-1]
        return "{: >6.2f}{}{}".format(number * mult, char, unit)

if __name__ == '__main__':
    app = PsuControlApp()
    app.preselectPort()
    app.updatePorts()
    app.run()
