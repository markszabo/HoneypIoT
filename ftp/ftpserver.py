#!/usr/bin/env python2
# coding: utf-8
# Based on: https://gist.github.com/scturtle/1035886

import os,socket,threading,time,logging,random,urllib2
#import traceback

TEST = True #if testing on local machine
RPI = False

allow_delete = False
local_ip = socket.gethostbyname(socket.gethostname())
if RPI: #on the raspberry pi the gethostname will return 127.0.0.1, so let's use its ip
  local_ip = "192.168.1.101"
public_ip = urllib2.urlopen('http://ip.42.pl/raw').read()
if TEST:
  public_ip = local_ip
if TEST or RPI:
  local_port = 8888
else:
  local_port = 21
pasv_port_from = 8889
pasv_port_to = 9888
currdir=os.path.abspath('files')

globallog = logging.getLogger('ftpserver')
hdlr = logging.FileHandler('log/ftp_global.log')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
hdlr.setFormatter(formatter)
globallog.addHandler(hdlr) 
globallog.setLevel(logging.DEBUG) #log all messages
globallog.info('Ftp server started')

loginlog = logging.getLogger('ftpserver_logins')
loginhdlr = logging.FileHandler('log/ftp_logins.log')
loginhdlr.setFormatter(formatter)
loginlog.addHandler(loginhdlr) 
loginlog.setLevel(logging.DEBUG) #log all messages
loginlog.info('Logins log started')
loginlog.info("Remote IP\tUsername\tPassword")

uploadlog = logging.getLogger('ftpserver_uploads')
uploadhdlr = logging.FileHandler('log/ftp_uploads.log')
uploadhdlr.setFormatter(formatter)
uploadlog.addHandler(uploadhdlr) 
uploadlog.setLevel(logging.DEBUG) #log all messages
uploadlog.info('Uploads log started')
uploadlog.info("Remote IP\tUsername\tPassword\tOriginal filename\tStored filename")

class FTPserverThread(threading.Thread):
    def __init__(self,(conn,addr)):
        self.conn=conn
        self.addr=addr
        self.basewd=currdir
        self.cwd=self.basewd
        self.rest=False
        self.pasv_mode=False
        
        self.logfile="log/ftp_ind_" + time.strftime("%Y.%m.%d_%H:%M:%S") + "_" + str(addr)
        self.log=logging.getLogger('ftpserver'+self.logfile)
        self.hdlr=logging.FileHandler(self.logfile)
        self.hdlr.setFormatter(formatter)
        self.log.addHandler(self.hdlr)
        self.log.setLevel(logging.DEBUG)
        self.log.info(str(addr) + " connected")
        threading.Thread.__init__(self)

    def run(self):
        self.conn.send('220 Welcome!\r\n')
        while True:
            cmd=self.conn.recv(256)
            if not cmd: break
            else:
                self.print_and_log('Recieved:' + str(cmd))
                try:
                    func=getattr(self,cmd[:4].strip().upper())
                    func(cmd)
                except Exception,e:
                    self.print_and_log('ERROR:' + str(e))
                    #traceback.print_exc()
                    self.conn.send('500 Sorry.\r\n')

    def print_and_log(self,text):
        print text
        globallog.info(text)
        self.log.info(text)
    def SYST(self,cmd):
        self.conn.send('215 UNIX Type: L8\r\n')
    def OPTS(self,cmd):
        if cmd[5:-2].upper()=='UTF8 ON':
            self.conn.send('200 OK.\r\n')
        else:
            self.conn.send('451 Sorry.\r\n')
    def USER(self,cmd):
        self.username = cmd[4:].strip()
        self.conn.send('331 OK.\r\n')
    def PASS(self,cmd):
        self.password = cmd[4:].strip()
        loginlog.info(str(self.addr) + "\t" + self.username + "\t" + self.password)
        self.conn.send('230 OK.\r\n')
        #self.conn.send('530 Incorrect.\r\n')
    def QUIT(self,cmd):
        self.conn.send('221 Goodbye.\r\n')
    def NOOP(self,cmd):
        self.conn.send('200 OK.\r\n')
    def TYPE(self,cmd):
        self.mode=cmd[5]
        self.conn.send('200 Binary mode.\r\n')

    def CDUP(self,cmd):
        if not os.path.samefile(self.cwd,self.basewd):
            #learn from stackoverflow
            self.cwd=os.path.abspath(os.path.join(self.cwd,'..'))
        self.conn.send('200 OK.\r\n')
    def PWD(self,cmd):
        cwd=os.path.relpath(self.cwd,self.basewd)
        if cwd=='.':
            cwd='/'
        else:
            cwd='/'+cwd
        self.conn.send('257 \"%s\"\r\n' % cwd)
    def CWD(self,cmd):
        chwd=cmd[4:-2]
        if ".." in chwd:
          self.conn.send('550 Permission denied\r\n')
        elif chwd=='/':
            self.cwd=self.basewd
        elif chwd[0]=='/':
            self.cwd=os.path.join(self.basewd,chwd[1:])
        else:
            self.cwd=os.path.join(self.cwd,chwd)
        self.conn.send('250 OK.\r\n')

    def PORT(self,cmd):
        if self.pasv_mode:
            self.servsock.close()
            self.pasv_mode = False
        l=cmd[5:].split(',')
        self.dataAddr='.'.join(l[:4])
        self.dataPort=(int(l[4])<<8)+int(l[5])
        self.conn.send('200 Get port.\r\n')

    def PASV(self,cmd): # from http://goo.gl/3if2U
        self.pasv_mode = True
        self.servsock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.servsock.bind((local_ip,random.randint(pasv_port_from,pasv_port_to)))
        self.servsock.listen(1)
        ip, port = self.servsock.getsockname()
        self.print_and_log('Passive Mode started on ' + str(ip) + ":" + str(port))
        self.conn.send('227 Entering Passive Mode (%s,%u,%u).\r\n' %
                (','.join(public_ip.split('.')), port>>8&0xFF, port&0xFF))

    def start_datasock(self):
        if self.pasv_mode:
            self.datasock, addr = self.servsock.accept()
            self.print_and_log('connect:' + str(addr))
        else:
            self.datasock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            self.datasock.connect((self.dataAddr,self.dataPort))

    def stop_datasock(self):
        self.datasock.close()
        if self.pasv_mode:
            self.servsock.close()


    def LIST(self,cmd):
        self.conn.send('150 Here comes the directory listing.\r\n')
        self.print_and_log('list:' + str(self.cwd))
        self.start_datasock()
        for t in os.listdir(self.cwd):
            k=self.toListItem(os.path.join(self.cwd,t))
            self.datasock.send(k+'\r\n')
        self.stop_datasock()
        self.conn.send('226 Directory send OK.\r\n')

    def toListItem(self,fn):
        st=os.stat(fn)
        fullmode='rwxrwxrwx'
        mode=''
        for i in range(9):
            mode+=((st.st_mode>>(8-i))&1) and fullmode[i] or '-'
        d=(os.path.isdir(fn)) and 'd' or '-'
        ftime=time.strftime(' %b %d %H:%M ', time.gmtime(st.st_mtime))
        return d+mode+' 1 user group '+str(st.st_size)+ftime+os.path.basename(fn)

    def MKD(self,cmd):
        dn=os.path.join(self.cwd,cmd[4:-2])
        os.mkdir(dn)
        self.conn.send('257 Directory created.\r\n')

    def RMD(self,cmd):
        dn=os.path.join(self.cwd,cmd[4:-2])
        if allow_delete:
            os.rmdir(dn)
            self.conn.send('250 Directory deleted.\r\n')
        else:
            self.conn.send('450 Not allowed.\r\n')

    def DELE(self,cmd):
        fn=os.path.join(self.cwd,cmd[5:-2])
        if allow_delete:
            os.remove(fn)
            self.conn.send('250 File deleted.\r\n')
        else:
            self.conn.send('450 Not allowed.\r\n')

    def RNFR(self,cmd):
        self.rnfn=os.path.join(self.cwd,cmd[5:-2])
        self.conn.send('350 Ready.\r\n')

    def RNTO(self,cmd):
        fn=os.path.join(self.cwd,cmd[5:-2])
        os.rename(self.rnfn,fn)
        self.conn.send('250 File renamed.\r\n')

    def REST(self,cmd):
        self.pos=int(cmd[5:-2])
        self.rest=True
        self.conn.send('250 File position reseted.\r\n')

    def RETR(self,cmd):
        fn=os.path.join(self.cwd,cmd[5:-2])
        #fn=os.path.join(self.cwd,cmd[5:-2]).lstrip('/')
        self.print_and_log('Downloading:' + str(fn))
        if self.mode=='I':
            fi=open(fn,'rb')
        else:
            fi=open(fn,'r')
        self.conn.send('150 Opening data connection.\r\n')
        if self.rest:
            fi.seek(self.pos)
            self.rest=False
        data= fi.read(1024)
        self.start_datasock()
        while data:
            self.datasock.send(data)
            data=fi.read(1024)
        fi.close()
        self.stop_datasock()
        self.conn.send('226 Transfer complete.\r\n')

    def STOR(self,cmd):
        fn = os.path.join(self.cwd,cmd[5:-2].lstrip("/"))
        i = 2
        while os.path.isfile(fn):
          fn = os.path.join(self.cwd,"["+str(i)+"]"+cmd[5:-2].lstrip("/"))
          i += 1
        self.print_and_log('Uploading: ' + cmd[5:-2].lstrip("/") + ' into: ' + str(fn))
        uploadlog.info(str(self.addr) + "\t" + self.username + "\t" + self.password + "\t" + cmd[5:-2].lstrip("/") + "\t" + str(fn))
        if self.mode=='I':
            fo=open(fn,'wb')
        else:
            fo=open(fn,'w')
        self.conn.send('150 Opening data connection.\r\n')
        self.start_datasock()
        while True:
            data=self.datasock.recv(1024)
            if not data: break
            fo.write(data)
        fo.close()
        self.stop_datasock()
        self.conn.send('226 Transfer complete.\r\n')

class FTPserver(threading.Thread):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((local_ip,local_port))
        threading.Thread.__init__(self)

    def run(self):
        self.sock.listen(5)
        while True:
            th=FTPserverThread(self.sock.accept())
            th.daemon=True
            th.start()

    def stop(self):
        self.sock.close()

if __name__=='__main__':
    ftp=FTPserver()
    ftp.daemon=True
    ftp.start()
    print ('On ' + str(local_ip) + ':' + str(local_port))
    globallog.info('On ' + str(local_ip) + ':' + str(local_port))
    while True:
      time.sleep(1)
    ftp.stop()
